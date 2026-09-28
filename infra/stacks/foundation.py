"""Foundation: the pieces SageMaker training needs before any model exists."""
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class FoundationStack(Stack):
    def __init__(self, scope: Construct, cid: str, **kw):
        super().__init__(scope, cid, **kw)

        self.artifact_bucket = s3.Bucket(
            self, "Artifacts",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,   # POC: tear down cleanly
            auto_delete_objects=True,
        )

        # Least-privilege role used by SageMaker training jobs AND model hosting
        self.sagemaker_role = iam.Role(
            self, "SageMakerRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            description="Claims Triage POC - SageMaker training + hosting",
        )
        self.artifact_bucket.grant_read_write(self.sagemaker_role)
        self.sagemaker_role.add_to_policy(iam.PolicyStatement(
            actions=["ecr:GetAuthorizationToken", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
                     "ecr:BatchCheckLayerAvailability"],
            resources=["*"]))
        self.sagemaker_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                     "logs:DescribeLogStreams", "cloudwatch:PutMetricData"],
            resources=["*"]))

        CfnOutput(self, "ArtifactBucketName", value=self.artifact_bucket.bucket_name)
        CfnOutput(self, "SageMakerRoleArn", value=self.sagemaker_role.role_arn)
