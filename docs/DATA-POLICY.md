# Política de dados

1. **Nenhum dado real de cliente no repositório.** Código, testes, fixtures, capturas de tela e documentação usam dados
   claramente fictícios (ex.: "Maria Silva", `example.com`, `example.invalid`).
2. **Coletar o mínimo.** O núcleo só grava o que o sistema informa ou o técnico digita para o atendimento. Nada de coleta
   oculta ou telemetria.
3. **Dados de teste reais só localmente**, fora do Git (`.env`, `*.db`, `reports/`, `backups/` estão no `.gitignore`).
4. **Laudos e relatórios** gerados com dados de clientes ficam em `reports/` local e não são versionados.
5. **Credenciais** vêm de variáveis de ambiente ou do cofre do sistema, nunca de arquivos versionados.
6. O scanner (`scripts/scan_secrets.py`) procura CPF, CNPJ, telefones brasileiros e e-mails reais; falsos positivos
   legítimos são marcados com `nexus:allow-secret` na própria linha, com justificativa em revisão.
