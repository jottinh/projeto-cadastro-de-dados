import json
from pathlib import Path
from datetime import datetime

ARQUIVO_DADOS = Path("clientes_banco.json")

TIPOS_CONTA = ("Corrente", "Poupanca")


def carregar_clientes():
    if not ARQUIVO_DADOS.exists():
        return []

    try:
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except:
        return []


def salvar_clientes(clientes):
    with open(ARQUIVO_DADOS, "w", encoding="utf-8") as arquivo:
        json.dump(clientes, arquivo, ensure_ascii=False, indent=4)


def validar_cpf(cpf):
    cpf = ''.join(filter(str.isdigit, cpf))

    if len(cpf) != 11:
        return None

    if cpf == cpf[0] * 11:
        return None

    return cpf


def proximo_numero_conta(clientes):
    if not clientes:
        return "10000001"

    ultimo = max(int(cliente["conta"]) for cliente in clientes)

    return str(ultimo + 1)


def localizar_cliente_por_cpf(clientes, cpf):
    for cliente in clientes:
        if cliente["cpf"] == cpf:
            return cliente
    return None


def localizar_cliente_por_conta(clientes, conta):
    for cliente in clientes:
        if cliente["conta"] == conta:
            return cliente
    return None


def cadastrar_cliente(clientes):
    print("\n=== CADASTRO ===")

    nome = input("Nome: ")
    telefone = input("Telefone: ")
    email = input("Email: ")
    senha = input("Senha: ")

    while True:
        cpf = validar_cpf(input("CPF: "))

        if cpf is None:
            print("CPF inválido.")
            continue

        if localizar_cliente_por_cpf(clientes, cpf):
            print("CPF já cadastrado.")
            continue

        break

    print("\n1 - Corrente")
    print("2 - Poupança")

    opcao = input("Escolha: ")

    tipo_conta = "Corrente" if opcao == "1" else "Poupanca"

    cliente = {
        "nome": nome,
        "cpf": cpf,
        "telefone": telefone,
        "email": email,
        "senha": senha,
        "tipo_conta": tipo_conta,
        "agencia": "0001",
        "conta": proximo_numero_conta(clientes),
        "saldo": 0.00,
        "status": "Ativa",
        "data_abertura": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "extrato": []
    }

    clientes.append(cliente)

    salvar_clientes(clientes)

    print("\nCadastro realizado com sucesso!")
    print("Conta:", cliente["conta"])


def listar_clientes(clientes):

    print("\n=== CLIENTES ===")

    if not clientes:
        print("Nenhum cliente cadastrado.")
        return

    for cliente in clientes:

        print("-" * 50)

        print("Conta:", cliente["conta"])
        print("Nome:", cliente["nome"])
        print("CPF:", cliente["cpf"])
        print("Telefone:", cliente["telefone"])
        print("Tipo:", cliente["tipo_conta"])
        print("Saldo: R$", cliente["saldo"])


def depositar(clientes):

    conta = input("Número da conta: ")

    cliente = localizar_cliente_por_conta(clientes, conta)

    if not cliente:
        print("Conta não encontrada.")
        return

    valor = float(input("Valor do depósito: R$ "))

    if valor <= 0:
        print("Valor inválido.")
        return

    cliente["saldo"] += valor

    cliente["extrato"].append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo": "Depósito",
        "valor": valor
    })

    salvar_clientes(clientes)

    print(f"Depósito realizado. Saldo atual: R$ {cliente['saldo']:.2f}")


def sacar(clientes):

    conta = input("Número da conta: ")

    cliente = localizar_cliente_por_conta(clientes, conta)

    if not cliente:
        print("Conta não encontrada.")
        return

    valor = float(input("Valor do saque: R$ "))

    if valor <= 0:
        print("Valor inválido.")
        return

    if valor > cliente["saldo"]:
        print("Saldo insuficiente.")
        return

    cliente["saldo"] -= valor

    cliente["extrato"].append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo": "Saque",
        "valor": valor
    })

    salvar_clientes(clientes)

    print(f"Saque realizado. Saldo atual: R$ {cliente['saldo']:.2f}")


def pix(clientes):

    origem = input("Conta origem: ")
    destino = input("Conta destino: ")

    valor = float(input("Valor: R$ "))

    conta_origem = localizar_cliente_por_conta(clientes, origem)
    conta_destino = localizar_cliente_por_conta(clientes, destino)

    if not conta_origem:
        print("Conta de origem não encontrada.")
        return

    if not conta_destino:
        print("Conta de destino não encontrada.")
        return

    if conta_origem["saldo"] < valor:
        print("Saldo insuficiente.")
        return

    conta_origem["saldo"] -= valor
    conta_destino["saldo"] += valor

    conta_origem["extrato"].append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo": "PIX Enviado",
        "valor": valor
    })

    conta_destino["extrato"].append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo": "PIX Recebido",
        "valor": valor
    })

    salvar_clientes(clientes)

    print("PIX realizado com sucesso!")


def ver_extrato(clientes):

    conta = input("Número da conta: ")

    cliente = localizar_cliente_por_conta(clientes, conta)

    if not cliente:
        print("Conta não encontrada.")
        return

    print("\n=== EXTRATO ===")

    print("Titular:", cliente["nome"])
    print("Saldo: R$", f"{cliente['saldo']:.2f}")

    print("-" * 50)

    if not cliente["extrato"]:
        print("Nenhuma movimentação.")
        return

    for item in cliente["extrato"]:

        print(
            f"{item['data']} | {item['tipo']} | R$ {item['valor']:.2f}"
        )


def atualizar_cliente(clientes):

    cpf = input("CPF: ")

    cliente = localizar_cliente_por_cpf(clientes, cpf)

    if not cliente:
        print("Cliente não encontrado.")
        return

    cliente["nome"] = input(
        f"Nome ({cliente['nome']}): "
    ) or cliente["nome"]

    cliente["telefone"] = input(
        f"Telefone ({cliente['telefone']}): "
    ) or cliente["telefone"]

    salvar_clientes(clientes)

    print("Cadastro atualizado.")


def excluir_cliente(clientes):

    cpf = input("CPF: ")

    cliente = localizar_cliente_por_cpf(clientes, cpf)

    if not cliente:
        print("Cliente não encontrado.")
        return

    confirmacao = input(
        f"Excluir {cliente['nome']}? (s/n): "
    ).lower()

    if confirmacao == "s":
        clientes.remove(cliente)

        salvar_clientes(clientes)

        print("Cliente removido.")


def main():

    clientes = carregar_clientes()

    while True:

        print("\n===== FIRST SYSTEM BANK =====")
        print("1 - Cadastrar Cliente")
        print("2 - Listar Clientes")
        print("3 - Atualizar Cadastro")
        print("4 - Excluir Cliente")
        print("5 - Depositar")
        print("6 - Sacar")
        print("7 - PIX")
        print("8 - Extrato")
        print("0 - Sair")

        opcao = input("Escolha: ")

        if opcao == "1":
            cadastrar_cliente(clientes)

        elif opcao == "2":
            listar_clientes(clientes)

        elif opcao == "3":
            atualizar_cliente(clientes)

        elif opcao == "4":
            excluir_cliente(clientes)

        elif opcao == "5":
            depositar(clientes)

        elif opcao == "6":
            sacar(clientes)

        elif opcao == "7":
            pix(clientes)

        elif opcao == "8":
            ver_extrato(clientes)

        elif opcao == "0":
            print("Sistema encerrado.")
            break

        else:
            print("Opção inválida.")


if __name__ == "__main__":
    main()