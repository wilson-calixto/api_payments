import json

import aws_cdk as core
import aws_cdk.assertions as assertions

from api_payments.api_payments_stack import ApiPaymentsStack


def test_payment_pipeline_resources():
    app = core.App()
    stack = ApiPaymentsStack(app, "api-payments")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::SQS::Queue", 3)
    template.resource_count_is("AWS::Pipes::Pipe", 1)
    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)
    template.has_resource_properties("AWS::Lambda::Function", {
        "Handler": "validate_order.handler",
        "Runtime": "python3.12",
    })
    template.has_resource_properties("AWS::Lambda::Function", {
        "Handler": "process_payment.handler",
        "Runtime": "python3.12",
    })

    template.has_resource_properties("AWS::Pipes::Pipe", {
        "SourceParameters": {
            "SqsQueueParameters": {
                "BatchSize": 1,
            }
        },
        "TargetParameters": {
            "InputTemplate": '{"valor": <$.body.valor>, "userId": <$.body.userId>}',
            "StepFunctionStateMachineParameters": {
                "InvocationType": "REQUEST_RESPONSE",
            },
        },
    })

    template.has_resource_properties("AWS::StepFunctions::StateMachine", {
        "StateMachineType": "EXPRESS",
    })
    state_machine_template = json.dumps(template.to_json())
    assert "Normalize Pipe Input" in state_machine_template
    assert "$[0].valor" in state_machine_template
    assert "$[0].userId" in state_machine_template

    template.has_resource_properties("AWS::ApiGateway::Resource", {
        "PathPart": "payments",
    })
    template.has_resource_properties("AWS::ApiGateway::Resource", {
        "PathPart": "example",
    })
