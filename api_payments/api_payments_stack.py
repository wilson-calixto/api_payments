from constructs import Construct
from aws_cdk import (
    Aws,
    CfnOutput,
    CfnParameter,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigw,
    aws_cloudwatch as cloudwatch,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_pipes as pipes,
    aws_ses as ses,
    aws_sqs as sqs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    custom_resources as cr,
)


class ApiPaymentsStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        sender_email = CfnParameter(
            self,
            "SenderEmail",
            type="String",
            default="wilson.calixto.c.junior@gmail.com",
            description="Verified SES sender address used for payment notifications.",
        )
        users_table = dynamodb.Table(
            self,
            "PaymentUsers",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
        notification_table = dynamodb.Table(
            self,
            "PaymentEmailNotifications",
            partition_key=dynamodb.Attribute(
                name="notificationId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expiresAt",
            removal_policy=RemovalPolicy.RETAIN,
        )
        transactions_table = dynamodb.Table(
            self,
            "PaymentTransactions",
            partition_key=dynamodb.Attribute(name="paymentId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
        payment_events_table = dynamodb.Table(
            self,
            "PaymentEvents",
            partition_key=dynamodb.Attribute(name="eventId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
        self._seed_users(users_table)

        queue_name = "api-payments-queue"
        dead_letter_queue_name = "api-payments-dead-letter-queue"

        dead_letter_queue = sqs.Queue(
            self,
            dead_letter_queue_name,
            queue_name=dead_letter_queue_name,
        )
        queue = sqs.Queue(
            self,
            queue_name,
            queue_name=queue_name,
            visibility_timeout=Duration.minutes(5),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dead_letter_queue,
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
                resources=[dead_letter_queue.queue_arn],
            )
        )

        rest_api_role = iam.Role(
            self,
            "RestAPIRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
        )
        queue.grant_send_messages(rest_api_role)

        base_api = apigw.RestApi(self, "ApiGW", rest_api_name="TestAPI")
        base_api.root.add_method("ANY")
        self._add_sqs_post_method(base_api.root.add_resource("example"), rest_api_role, queue)
        payments_resource = base_api.root.add_resource("payments")
        payment_request_model = apigw.Model(
            self,
            "PaymentRequestModel",
            rest_api=base_api,
            content_type="application/json",
            model_name="PaymentRequest",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT4,
                title="Payment request",
                type=apigw.JsonSchemaType.OBJECT,
                required=["valor", "userId"],
                properties={
                    "valor": apigw.JsonSchema(type=apigw.JsonSchemaType.NUMBER),
                    "userId": apigw.JsonSchema(
                        type=apigw.JsonSchemaType.STRING,
                        min_length=1,
                    ),
                },
            ),
        )
        payment_request_validator = apigw.RequestValidator(
            self,
            "PaymentRequestValidator",
            rest_api=base_api,
            validate_request_body=True,
        )
        apigw.GatewayResponse(
            self,
            "InvalidPaymentRequestResponse",
            rest_api=base_api,
            type=apigw.ResponseType.BAD_REQUEST_BODY,
            status_code="400",
            templates={
                "application/json": (
                    '{"message":"Payload inválido. Informe valor (número) e '
                    'userId (texto não vazio)."}'
                )
            },
        )
        self._add_sqs_post_method(
            payments_resource,
            rest_api_role,
            queue,
            request_validator=payment_request_validator,
            request_models={"application/json": payment_request_model},
        )


        sns_topic_payment_error = sns.Topic(self, "PaymentErrorNotifications")
        publish_to_sns_task_error = tasks.SnsPublish(
            self, "Publish Payment Error to SNS",
            topic=sns_topic_payment_error,
            message=sfn.TaskInput.from_object({
                "eventType": "PAYMENT_REJECTED",
                "userId": sfn.JsonPath.string_at("$.userId"),
                "paymentId": sfn.JsonPath.string_at("$.resultado_validacao.payment_id"),
                "amount": sfn.JsonPath.number_at("$.resultado_validacao.valor"),
                "reason": sfn.JsonPath.string_at("$.resultado_validacao.motivo"),
            }),
            subject="Payment Error, Step Functions State Machine finalized",
        )


        sns_topic_payment_success = sns.Topic(self, "PaymentSuccessNotifications")
        sns_delivery_log_role = iam.Role(
            self,
            "SnsDeliveryStatusLogRole",
            assumed_by=iam.ServicePrincipal("sns.amazonaws.com"),
            description="Allows SNS to write Lambda delivery status logs to CloudWatch Logs.",
        )
        sns_delivery_log_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[f"arn:{Aws.PARTITION}:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:*"],
            )
        )
        for topic in (sns_topic_payment_success, sns_topic_payment_error):
            topic.add_logging_config(
                protocol=sns.LoggingProtocol.LAMBDA,
                failure_feedback_role=sns_delivery_log_role,
                success_feedback_role=sns_delivery_log_role,
                success_feedback_sample_rate=100,
            )

        publish_to_sns_task_success = tasks.SnsPublish(
            self, "Publish Payment Success to SNS",
            topic=sns_topic_payment_success,
            message=sfn.TaskInput.from_object({
                "eventType": "PAYMENT_APPROVED",
                "userId": sfn.JsonPath.string_at("$.userId"),
                "paymentId": sfn.JsonPath.string_at("$.resultado_validacao.payment_id"),
                "amount": sfn.JsonPath.number_at("$.resultado_validacao.valor"),
                "transactionId": sfn.JsonPath.string_at("$.resultado_pagamento.transaction_id"),
                "eventId": sfn.JsonPath.string_at("$.resultado_persistencia.event_id"),
            }),
            subject="Payment success, Step Functions State Machine finalized",
        )


        lambda_code = _lambda.Code.from_asset("api_payments/src/lambda")

        validate_order_lambda = _lambda.Function(
            self, "ValidateOrderFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="validate_order.handler",
            code=lambda_code,
            timeout=Duration.seconds(30),
        )

        process_payment_lambda = _lambda.Function(
            self, "ProcessPaymentFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="process_payment.handler",
            code=lambda_code,
            timeout=Duration.seconds(30),
        )
        record_payment_lambda = _lambda.Function(
            self,
            "RecordApprovedPaymentFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="record_payment.handler",
            code=lambda_code,
            timeout=Duration.seconds(30),
            environment={
                "TRANSACTIONS_TABLE_NAME": transactions_table.table_name,
                "PAYMENT_EVENTS_TABLE_NAME": payment_events_table.table_name,
            },
        )
        transactions_table.grant_read_write_data(record_payment_lambda)
        payment_events_table.grant_read_write_data(record_payment_lambda)
        notification_lambda = _lambda.Function(
            self,
            "PaymentNotificationFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="send_payment_notification.handler",
            code=lambda_code,
            timeout=Duration.seconds(30),
            environment={
                "USERS_TABLE_NAME": users_table.table_name,
                "NOTIFICATIONS_TABLE_NAME": notification_table.table_name,
                "SENDER_EMAIL": sender_email.value_as_string,
            },
        )
        users_table.grant_read_data(notification_lambda)
        notification_table.grant_read_write_data(notification_lambda)
        notification_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail"],
                resources=["*"],
                conditions={
                    "StringEquals": {"ses:FromAddress": sender_email.value_as_string}
                },
            )
        )
        ses.EmailIdentity(
            self,
            "PaymentNotificationSenderIdentity",
            identity=ses.Identity.email(sender_email.value_as_string),
        )
        notification_dead_letter_queue = sqs.Queue(
            self,
            "PaymentNotificationDeadLetterQueue",
            queue_name="api-payments-notification-dead-letter-queue",
            retention_period=Duration.days(14),
        )
        sns_topic_payment_success.add_subscription(
            subscriptions.LambdaSubscription(
                notification_lambda,
                dead_letter_queue=notification_dead_letter_queue,
            )
        )

        reconciliation_lambda = _lambda.Function(
            self,
            "PaymentReconciliationFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="reconcile_payment.handler",
            code=lambda_code,
            timeout=Duration.seconds(30),
            environment={
                "TRANSACTIONS_TABLE_NAME": transactions_table.table_name,
                "PAYMENT_EVENTS_TABLE_NAME": payment_events_table.table_name,
            },
        )
        transactions_table.grant_read_write_data(reconciliation_lambda)
        payment_events_table.grant_read_write_data(reconciliation_lambda)
        sns_topic_payment_success.add_subscription(
            subscriptions.LambdaSubscription(
                reconciliation_lambda,
                dead_letter_queue=notification_dead_letter_queue,
            )
        )
        sns_topic_payment_error.add_subscription(
            subscriptions.LambdaSubscription(
                notification_lambda,
                dead_letter_queue=notification_dead_letter_queue,
            )
        )

        task_validate_order = tasks.LambdaInvoke(
            self, "Validate Order",
            lambda_function=validate_order_lambda,
            payload_response_only=True,
            result_path="$.resultado_validacao",
        )

        task_payment = tasks.LambdaInvoke(
            self, "Process Payment",
            lambda_function=process_payment_lambda,
            payload_response_only=True,
            result_path="$.resultado_pagamento",
        )
        task_payment.add_retry(
            errors=["States.ALL"],
            interval=Duration.seconds(2),
            max_attempts=3,
            backoff_rate=2.0,
        )
        task_record_payment = tasks.LambdaInvoke(
            self,
            "Persist Approved Payment",
            lambda_function=record_payment_lambda,
            payload_response_only=True,
            result_path="$.resultado_persistencia",
        )
        task_record_payment.add_retry(
            errors=["States.ALL"],
            interval=Duration.seconds(2),
            max_attempts=3,
            backoff_rate=2.0,
        )

        decision_validation = sfn.Choice(self, "Is the order valid?")
        condition_approved = sfn.Condition.string_equals(
            "$.resultado_validacao.status", "APPROVED"
        )

        task_success = sfn.Succeed(
            self, "Success",
            comment="The order was approved and the payment was processed.",
        )
        task_order_rejected = sfn.Succeed(
            self, "Order Rejected",
            comment="The order did not pass the business validation.",
        )

        on_success = task_payment.next(task_record_payment).next(publish_to_sns_task_success).next(task_success)
        on_rejected = publish_to_sns_task_error.next(task_order_rejected)

        normalize_pipe_input = sfn.Pass(
            self,
            "Normalize Pipe Input",
            comment="EventBridge Pipes invokes Step Functions with a one-item batch.",
            parameters={
                "valor.$": "$[0].valor",
                "userId.$": "$[0].userId",
            },
        )
        flow = normalize_pipe_input.next(task_validate_order).next(
            decision_validation.when(
                condition_approved,
                on_success,
            ).otherwise(
                on_rejected,
            )
        )


        sfn_log_group = logs.LogGroup(
            self,
            "StateMachineLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        state_machine = sfn.StateMachine(
            self, "OrderProcessingStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(flow),
            state_machine_type=sfn.StateMachineType.EXPRESS,
            logs=sfn.LogOptions(
                destination=sfn_log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True,
            ),
            tracing_enabled=True,
        )

        pipe_log_group = logs.LogGroup(
            self,
            "PipeLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
        )
        pipe_role = iam.Role(
            self, "PipeRole",
            assumed_by=iam.ServicePrincipal("pipes.amazonaws.com"),
        )
        queue.grant_consume_messages(pipe_role)
        state_machine.grant_start_sync_execution(pipe_role)
        pipe_log_group.grant_write(pipe_role)
        pipe_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[
                    pipe_log_group.log_group_arn,
                    f"{pipe_log_group.log_group_arn}:*",
                ],
            )
        )

        pipes.CfnPipe(
            self, "SqsToStepFunctionsPipe",
            role_arn=pipe_role.role_arn,
            source=queue.queue_arn,
            target=state_machine.state_machine_arn,
            source_parameters=pipes.CfnPipe.PipeSourceParametersProperty(
                sqs_queue_parameters=pipes.CfnPipe.PipeSourceSqsQueueParametersProperty(
                    batch_size=1,
                )
            ),
            target_parameters=pipes.CfnPipe.PipeTargetParametersProperty(
                # SQS bodies are implicitly decoded by EventBridge Pipes. Passing
                # <$.body> alone removes the JSON quotes and makes Step Functions
                # reject the execution input. Build the target object explicitly.
                input_template='{"valor": <$.body.valor>, "userId": <$.body.userId>}',
                step_function_state_machine_parameters=pipes.CfnPipe.PipeTargetStateMachineParametersProperty(
                    invocation_type="REQUEST_RESPONSE",
                ),
            ),
            log_configuration=pipes.CfnPipe.PipeLogConfigurationProperty(
                cloudwatch_logs_log_destination=pipes.CfnPipe.CloudwatchLogsLogDestinationProperty(
                    log_group_arn=pipe_log_group.log_group_arn,
                ),
                level="INFO",
                include_execution_data=["ALL"],
            ),
        )

        cloudwatch.Alarm(
            self, "DlqMessagesAlarm",
            metric=dead_letter_queue.metric_approximate_number_of_messages_visible(),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        cloudwatch.Alarm(
            self,
            "NotificationDlqMessagesAlarm",
            metric=notification_dead_letter_queue.metric_approximate_number_of_messages_visible(),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        CfnOutput(self, "PaymentsUrl", value=f"{base_api.url}payments")
        CfnOutput(self, "ExampleUrl", value=f"{base_api.url}example")
        CfnOutput(self, "PaymentUsersTableName", value=users_table.table_name)
        CfnOutput(self, "PaymentTransactionsTableName", value=transactions_table.table_name)
        CfnOutput(self, "PaymentEventsTableName", value=payment_events_table.table_name)
        CfnOutput(self, "PaymentSuccessTopicArn", value=sns_topic_payment_success.topic_arn)
        CfnOutput(
            self,
            "NotificationDeadLetterQueueUrl",
            value=notification_dead_letter_queue.queue_url,
        )
        CfnOutput(
            self,
            "PaymentsPayloadHint",
            value='POST JSON {"valor": 100, "userId": "user-001"}',
        )

    def _add_sqs_post_method(
        self,
        resource: apigw.Resource,
        rest_api_role: iam.Role,
        queue: sqs.Queue,
        request_validator: apigw.IRequestValidator | None = None,
        request_models: dict[str, apigw.IModel] | None = None,
    ) -> None:
        integration_response = apigw.IntegrationResponse(
            status_code="200",
            response_templates={
                "application/json": '{"ok": true, "queue": "api-payments-queue"}',
            },
        )
        api_integration_options = apigw.IntegrationOptions(
            credentials_role=rest_api_role,
            integration_responses=[integration_response],
            request_templates={
                "application/json": "Action=SendMessage&MessageBody=$util.urlEncode($input.body)",
            },
            passthrough_behavior=apigw.PassthroughBehavior.NEVER,
            request_parameters={
                "integration.request.header.Content-Type": "'application/x-www-form-urlencoded'",
            },
        )
        api_resource_sqs_integration = apigw.AwsIntegration(
            service="sqs",
            integration_http_method="POST",
            path="{}/{}".format(Aws.ACCOUNT_ID, queue.queue_name),
            options=api_integration_options,
        )
        resource.add_method(
            "POST",
            api_resource_sqs_integration,
            method_responses=[apigw.MethodResponse(status_code="200")],
            request_validator=request_validator,
            request_models=request_models,
        )

    def _seed_users(self, users_table: dynamodb.Table) -> None:
        """Create sample users once without overwriting later profile changes."""
        users = [
            ("user-001", "Ana Silva", "ana.silva@example.com"),
            ("user-002", "Bruno Costa", "bruno.costa@example.com"),
            ("user-003", "Carla Souza", "carla.souza@example.com"),
            ("user-004", "Diego Lima", "diego.lima@example.com"),
            ("user-005", "Elisa Rocha", "elisa.rocha@example.com"),
            ("user-006", "Felipe Alves", "felipe.alves@example.com"),
            ("user-007", "Gabriela Nunes", "gabriela.nunes@example.com"),
            ("user-008", "Henrique Melo", "henrique.melo@example.com"),
            ("user-009", "Isabela Ramos", "isabela.ramos@example.com"),
            ("user-010", "João Freitas", "joao.freitas@example.com"),
        ]

        for user_id, name, email in users:
            cr.AwsCustomResource(
                self,
                f"Seed{user_id.replace('-', '').title()}",
                on_create=cr.AwsSdkCall(
                    service="DynamoDB",
                    action="putItem",
                    parameters={
                        "TableName": users_table.table_name,
                        "Item": {
                            "userId": {"S": user_id},
                            "name": {"S": name},
                            "email": {"S": email},
                            "emailVerified": {"BOOL": False},
                        },
                        "ConditionExpression": "attribute_not_exists(userId)",
                    },
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"payment-user-seed-{user_id}"
                    ),
                    ignore_error_codes_matching="ConditionalCheckFailedException",
                ),
                policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                    resources=[users_table.table_arn]
                ),
            )
