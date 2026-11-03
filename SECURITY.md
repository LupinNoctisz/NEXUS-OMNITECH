# Política de segurança

## Reportar uma vulnerabilidade
Não abra uma issue pública com detalhes de uma falha. Use **Security > Report a vulnerability** neste repositório
(relato privado do GitHub; precisa estar habilitado nas configurações do repositório) ou fale diretamente com a LMF Informática.

## O que NUNCA deve ser enviado ao repositório
Senhas, tokens, chaves de API, chaves privadas, arquivos `.env`, bancos `.db`, logs e backups locais, segredos ou chaves
de licenciamento/assinatura, e **qualquer dado real de clientes da LMF Informática** (nomes, CPF/CNPJ, telefones, e-mails,
números de série ligados a pessoas, laudos). Testes e documentação usam apenas dados fictícios.

## Como o repositório se protege
- `.gitignore` cobre `.env.*`, chaves, bancos e artefatos; só `.env.example` (valores fictícios) é versionado.
- `scripts/scan_secrets.py` varre segredos e dados pessoais; roda no hook `pre-commit` (ative com
  `git config core.hooksPath .githooks`) e no CI a cada push.
- `CODEOWNERS` e Dependabot estão configurados em `.github/`.

Se um segredo for commitado por engano: **revogue-o imediatamente** no serviço de origem, gere outro e avise o responsável.
Apagar o arquivo não basta, porque o valor continua no histórico do Git.

Detalhes técnicos e limitações conhecidas: [docs/SECURITY.md](docs/SECURITY.md).
