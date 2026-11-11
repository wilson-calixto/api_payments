
# Welcome to your CDK Python project!

This is a blank project for CDK development with Python.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdk synth
```

To add additional dependencies, for example other CDK libraries, just add
them to your `requirements.txt` file and rerun the `python -m pip install -r requirements.txt`
command.

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!

## Notificações de pagamento por e-mail

O fluxo de pagamento recebe `valor` e `userId`, publica o resultado em um dos
tópicos SNS existentes e uma Lambda de notificação busca o usuário no DynamoDB
antes de enviar o e-mail pelo Amazon SES.

```json
{
  "valor": 100,
  "userId": "user-001"
}
```

O deploy cria duas tabelas:

- `PaymentUsers`: usuários identificados por `userId`;
- `PaymentEmailNotifications`: controle de mensagens SNS já processadas, para
  reduzir e-mails duplicados em tentativas de entrega.

Dez usuários de exemplo são incluídos durante a criação da stack. Eles usam
endereços `example.com` e começam com `emailVerified=false`; portanto, não
recebem e-mails. Antes de usar o fluxo, substitua cada `email` por um endereço
real autorizado e defina `emailVerified` como `true` no item correspondente.
Os seeds não sobrescrevem modificações feitas posteriormente na tabela.

O remetente é obrigatório no deploy e precisa ser uma identidade verificada no
SES. Exemplo:

```bash
cdk deploy --parameters SenderEmail=pagamentos@seu-dominio.com
```

Se a conta SES estiver em sandbox, cada destinatário também deve ser
verificado. Falhas permanentes de entrega da assinatura SNS são encaminhadas à
fila `api-payments-notification-dead-letter-queue`.
