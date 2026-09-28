"""Application: 3 SageMaker endpoints, orchestrator Lambda, API Gateway, DynamoDB, web console."""
import os

from aws_cdk import CfnOutput, CfnTag, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_sagemaker as sm
from constructs import Construct

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class AppStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, foundation, artifacts: dict, **kw):
        super().__init__(scope, cid, **kw)
        mode = self.node.try_get_context("endpoint_mode") or "serverless"
        instance = self.node.try_get_context("realtime_instance_type") or "ml.t2.medium"
        prefix = self.node.try_get_context("endpoint_prefix") or "claims-triage"

        # ------------------------------------------------------------ SageMaker endpoints
        endpoints = {}
        for name, a in artifacts["models"].items():
            model = sm.CfnModel(
                self, f"{name.title()}Model",
                execution_role_arn=foundation.sagemaker_role.role_arn,
                primary_container=sm.CfnModel.ContainerDefinitionProperty(
                    image=a["image"],
                    model_data_url=a["model_data"],
                    environment={
                        "SAGEMAKER_PROGRAM": a["entry_point"],
                        "SAGEMAKER_SUBMIT_DIRECTORY": "/opt/ml/model/code",
                        "SAGEMAKER_CONTAINER_LOG_LEVEL": "20",
                        "SAGEMAKER_REGION": self.region,
                    },
                ),
                tags=[CfnTag(key="project", value="claims-triage-poc")],
            )
            if mode == "realtime":
                variant = sm.CfnEndpointConfig.ProductionVariantProperty(
                    variant_name="AllTraffic", model_name=model.attr_model_name,
                    initial_instance_count=1, instance_type=instance, initial_variant_weight=1.0)
            else:
                variant = sm.CfnEndpointConfig.ProductionVariantProperty(
                    variant_name="AllTraffic", model_name=model.attr_model_name,
                    serverless_config=sm.CfnEndpointConfig.ServerlessConfigProperty(
                        max_concurrency=3, memory_size_in_mb=2048))
            cfg = sm.CfnEndpointConfig(self, f"{name.title()}Config", production_variants=[variant])
            ep_name = f"{prefix}-{name}"
            sm.CfnEndpoint(self, f"{name.title()}Endpoint",
                           endpoint_config_name=cfg.attr_endpoint_config_name,
                           endpoint_name=ep_name)
            endpoints[name] = ep_name

        # ------------------------------------------------------------ storage
        docs = s3.Bucket(
            self, "Documents",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True,
            lifecycle_rules=[s3.LifecycleRule(expiration=Duration.days(30))],
            cors=[s3.CorsRule(allowed_methods=[s3.HttpMethods.PUT], allowed_origins=["*"],
                              allowed_headers=["*"], max_age=3000)],
        )
        table = ddb.Table(
            self, "TriageResults",
            partition_key=ddb.Attribute(name="triage_id", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        table.add_global_secondary_index(
            index_name="by-created",
            partition_key=ddb.Attribute(name="pk", type=ddb.AttributeType.STRING),
            sort_key=ddb.Attribute(name="created_at", type=ddb.AttributeType.STRING))

        # ------------------------------------------------------------ orchestrator
        fn = lambda_.Function(
            self, "Orchestrator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="app.handler",
            code=lambda_.Code.from_asset(os.path.join(ROOT, "lambda", "orchestrator"),
                                         exclude=["__pycache__", "*.pyc"]),
            timeout=Duration.seconds(29),
            memory_size=512,
            log_group=logs.LogGroup(self, "OrchestratorLogs", retention=logs.RetentionDays.ONE_MONTH,
                                    removal_policy=RemovalPolicy.DESTROY),
            environment={
                "FRAUD_ENDPOINT": endpoints["fraud"],
                "SEVERITY_ENDPOINT": endpoints["severity"],
                "NOTES_ENDPOINT": endpoints["notes"],
                "TABLE_NAME": table.table_name,
                "DOC_BUCKET": docs.bucket_name,
            },
        )
        table.grant_read_write_data(fn)
        docs.grant_read_write(fn)
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["sagemaker:InvokeEndpoint", "sagemaker:DescribeEndpoint"],
            resources=[f"arn:aws:sagemaker:{self.region}:{self.account}:endpoint/{prefix}-*"]))
        fn.add_to_role_policy(iam.PolicyStatement(actions=["textract:DetectDocumentText"], resources=["*"]))

        if self.node.try_get_context("keep_warm") in (True, "true", None):
            events.Rule(self, "KeepWarm", schedule=events.Schedule.rate(Duration.minutes(5)),
                        targets=[targets.LambdaFunction(fn)])

        # ------------------------------------------------------------ API
        api = apigw.RestApi(
            self, "ClaimsTriageApi",
            rest_api_name="claims-triage-api",
            description="Claims Triage Assistant POC",
            deploy_options=apigw.StageOptions(stage_name="v1", throttling_rate_limit=10,
                                              throttling_burst_limit=20),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type", "x-api-key"]),
            # NB: api_key_required is set per method (below), NOT via default_method_options,
            # because defaults also apply to the CORS preflight OPTIONS methods and would break browsers.
        )
        for rtype in (apigw.ResponseType.DEFAULT_4_XX, apigw.ResponseType.DEFAULT_5_XX):
            api.add_gateway_response(f"Cors{rtype.response_type}", type=rtype, response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,x-api-key'"})
        integ = apigw.LambdaIntegration(fn)
        keyed = {"api_key_required": True}
        api.root.add_resource("health").add_method("GET", integ, **keyed)
        api.root.add_resource("triage").add_method("POST", integ, **keyed)
        documents = api.root.add_resource("documents")
        documents.add_method("POST", integ, **keyed)
        documents.add_resource("{document_id}").add_resource("triage").add_method("POST", integ, **keyed)
        claims = api.root.add_resource("claims")
        claims.add_method("GET", integ, **keyed)
        claims.add_resource("{triage_id}").add_method("GET", integ, **keyed)

        key = api.add_api_key("DemoKey", api_key_name="claims-triage-demo-key")
        plan = api.add_usage_plan("DemoPlan", name="claims-triage-demo",
                                  throttle=apigw.ThrottleSettings(rate_limit=10, burst_limit=20),
                                  quota=apigw.QuotaSettings(limit=20000, period=apigw.Period.MONTH))
        plan.add_api_key(key)
        plan.add_api_stage(stage=api.deployment_stage)

        # ------------------------------------------------------------ web console
        site = s3.Bucket(self, "ConsoleSite", block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                         encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
                         removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True)
        dist = cf.Distribution(
            self, "ConsoleCdn",
            default_root_object="index.html",
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_DISABLED),
            comment="Claims Triage POC console",
        )
        s3deploy.BucketDeployment(
            self, "ConsoleDeploy",
            destination_bucket=site, distribution=dist,
            sources=[s3deploy.Source.asset(os.path.join(ROOT, "web")),
                     s3deploy.Source.asset(os.path.join(ROOT, "sample_docs")),
                     s3deploy.Source.json_data("config.json", {"apiUrl": api.url})],
        )

        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "ApiKeyId", value=key.key_id)
        CfnOutput(self, "ConsoleUrl", value=f"https://{dist.distribution_domain_name}")
        CfnOutput(self, "GetApiKeyCommand",
                  value=f"aws apigateway get-api-key --api-key {key.key_id} --include-value "
                        f"--query value --output text --region {self.region}")
        for k, v in endpoints.items():
            CfnOutput(self, f"{k.title()}EndpointName", value=v)
