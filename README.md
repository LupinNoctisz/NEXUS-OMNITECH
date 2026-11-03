# NEXUS OMNITECH
**by LMF Informática** — *One platform. Every device. Technical control.*

Plataforma profissional de diagnóstico, manutenção e reparação tecnológica para técnicos e assistências técnicas.

> **Estado atual: Etapa 1 concluída (arquitetura e núcleo).** Existe o NEXUS CORE funcional e testado.
> Os módulos de diagnóstico (PC, Mobile, Console, Electronics Lab, Intelligence) estão **planejados** e
> aparecem como `planned` — nenhum deles gera resultados ainda. Não há interface gráfica nesta etapa.

## O que já funciona (NEXUS CORE)

| Área | Situação |
|---|---|
| Banco local SQLite com migrações versionadas | ✅ |
| Logs estruturados (JSON Lines), rotação e redação de credenciais | ✅ |
| Histórico de operações com hash encadeado (detecta adulteração) | ✅ |
| Papéis e permissões (viewer / technician / admin) | ✅ (identidade declarativa; ver SECURITY) |
| Configurações com validação | ✅ |
| Dispositivos: host local e USB (Linux sysfs / Windows PnP) + cadastro manual | ✅ (USB Windows não testado em Windows) |
| Sessões de diagnóstico | ✅ |
| Gerenciador de módulos: manifesto, hashes SHA-256, registro, ativar/desativar, carregamento | ✅ |
| Trava de operações destrutivas (confirmação + autorização + backup + auditoria) | ✅ |
| Backups com checksum e restauração segura | ✅ |
| Painel inicial (`nexus status`) com alertas reais | ✅ |
| Atualizador, gerenciador de drivers | ⏳ etapas seguintes |
| Sincronização, licenciamento | ⏳ etapa 8 |

## Requisitos
- Python 3.12 (alvo: 3.12.16). O núcleo usa **somente a biblioteca padrão**.
- Guia para Windows: [docs/INSTALL-WINDOWS.md](docs/INSTALL-WINDOWS.md)

## Uso rápido
```bash
python -m venv .venv && .venv/bin/pip install -e .[dev]   # Windows: .venv\Scripts\...
nexus init --admin "SEU NOME"
nexus --as "SEU NOME" status
nexus --as "SEU NOME" devices scan
nexus --as "SEU NOME" modules list
pytest
```
Os dados ficam em `%LOCALAPPDATA%\NexusOmnitech` (Windows) ou `~/.local/share/nexus-omnitech`; use `--home` ou `NEXUS_HOME` para mudar.

## Documentação
- [Arquitetura](docs/ARCHITECTURE.md)
- [Segurança e limitações conhecidas](docs/SECURITY.md)
- [Roadmap por etapas](docs/ROADMAP.md)

## Licença
Copyright © 2026 LMF Informática. Todos os direitos reservados. Veja [LICENSE](LICENSE).
