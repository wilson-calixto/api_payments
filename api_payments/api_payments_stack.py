from constructs import Construct
from aws_cdk import (
    aws_sqs as sqs,
    aws_iam as iam,
    aws_apigateway as apigw,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_event_source,
    Aws, Stack
)

class ApiPaymentsStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        #Create the SQS queue
        


        queue_name = 'api-payments-queue'
        dead_letter_queue_name = 'api-payments-dead-letter-queue'
        
        dead_letter_queue = sqs.Queue(
            self,
            dead_letter_queue_name,
            queue_name=f"{dead_letter_queue_name}",
        )
        queue = sqs.Queue(
            self,
            queue_name,
            queue_name=f"{queue_name}",
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dead_letter_queue, # Require dead letter queue to be created first
            ),
        )
        dead_letter_queue.add_to_resource_policy(
        statement=iam.PolicyStatement(
            actions=[
                "sqs:StartMessageMoveTask",
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes",
                "sqs:CancelMessageMoveTask",
                "sqs:ListMessageMoveTasks",
            ],
            effect=iam.Effect.ALLOW,
            principals=[iam.ServicePrincipal("sqs.amazonaws.com")],
            resources=[dead_letter_queue.queue_arn],
        )
        )
        dead_letter_queue.add_to_resource_policy(
            statement=iam.PolicyStatement(
                actions=["sqs:SendMessage"],
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("sqs.amazonaws.com")],
                resources=[queue.queue_arn],
            )
        )

        #Create the API GW service role with permissions to call SQS
        rest_api_role = iam.Role(
            self,
            "RestAPIRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSQSFullAccess")]
        )

        #Create an API GW Rest API
        base_api = apigw.RestApi(self, 'ApiGW',rest_api_name='TestAPI')
        base_api.root.add_method("ANY")

        #Create a resource named "example" on the base API
        api_resource = base_api.root.add_resource('example')


        #Create API Integration Response object: https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_apigateway/IntegrationResponse.html
        integration_response = apigw.IntegrationResponse(
            status_code="200",
            response_templates={"application/json": ""},

        )

        #Create API Integration Options object: https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_apigateway/IntegrationOptions.html
        api_integration_options = apigw.IntegrationOptions(
            credentials_role=rest_api_role,
            integration_responses=[integration_response],
            request_templates={"application/json": "Action=SendMessage&MessageBody=$input.body"},
            passthrough_behavior=apigw.PassthroughBehavior.NEVER,
            request_parameters={"integration.request.header.Content-Type": "'application/x-www-form-urlencoded'"},
        )

        #Create AWS Integration Object for SQS: https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_apigateway/AwsIntegration.html
        api_resource_sqs_integration = apigw.AwsIntegration(
            service="sqs",
            integration_http_method="POST",
            path="{}/{}".format(Aws.ACCOUNT_ID, queue.queue_name),
            options=api_integration_options
        )

        #Create a Method Response Object: https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_apigateway/MethodResponse.html
        method_response = apigw.MethodResponse(status_code="200")

        #Add the API GW Integration to the "example" API GW Resource
        api_resource.add_method(
            "POST",
            api_resource_sqs_integration,
            method_responses=[method_response]
        )

        #Creating Lambda function that will be triggered by the SQS Queue
        sqs_lambda = _lambda.Function(self,'SQSTriggerLambda',
            handler='lambda-handler.handler',
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset('lambda'),
        )

        #Create an SQS event source for Lambda
        sqs_event_source = lambda_event_source.SqsEventSource(queue)

        #Add SQS event source to the Lambda function
        sqs_lambda.add_event_source(sqs_event_source)