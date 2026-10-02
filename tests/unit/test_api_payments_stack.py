import aws_cdk as core
import aws_cdk.assertions as assertions

from api_payments.api_payments_stack import ApiPaymentsStack

# example tests. To run these tests, uncomment this file along with the example
# resource in api_payments/api_payments_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = ApiPaymentsStack(app, "api-payments")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
