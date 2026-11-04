# NEXUS OMNITECH
**by LMF Informática** — *One platform. Every device. Technical control.*

Plataforma profissional de diagnóstico, manutenção e reparação tecnológica para técnicos e assistências técnicas.

> **Estado atual: Etapa 1 (núcleo) e Fase 0 (segurança) concluídas; Etapa 2 (interface WPF + instalador) compilada, testada e instalada no CI do Windows; aparência ainda não revisada por um humano.**
> A interface (`ui/`) compila e passa 64 testes automáticos (incluindo ponta a ponta com o núcleo real), mas **ninguém abriu a janela ainda**:
> layout, cores e usabilidade precisam do seu teste no Windows. Veja [ui/README.md](ui/README.md).
> Os módulos de diagnóstico (PC, Mobile, Console, Electronics Lab, Intelligence) estão **planejados** e
> aparecem como `planned` / "Não implementado" — nenhum deles gera resultados ainda.

## O que já funciona (NEXUS CORE)

| Área | Situação |
|---|---|
| Banco local SQLite com migrações versionadas | ✅ |
| Logs estruturados (JSON Lines), rotação e redação de credenciais | ✅ |
| Histórico de operações com hash encadeado (detecta adulteração) | ✅ |
| Autenticação por senha (scrypt, bloqueio por tentativas) e papéis viewer / technician / admin | ✅ |
| Configurações com validação | ✅ |
| Dispositivos: host local e USB (Linux sysfs / Windows PnP) + cadastro manual | ✅ (USB Windows não testado em Windows) |
| Sessões de diagnóstico | ✅ |
| Gerenciador de módulos: manifesto, hashes SHA-256, registro, ativar/desativar, carregamento | ✅ |
| Trava de operações destrutivas (confirmação + autorização + backup + auditoria) | ✅ |
| Backups com checksum e restauração segura | ✅ |
| Painel inicial (`nexus status`) com alertas reais | ✅ |
| API local para a interface (JSON-RPC por stdio, lista fechada de métodos) | ✅ |
| Interface WPF (login, 8 seções, tema escuro/claro) com dados reais do núcleo | 🟡 compila, testa e instala/abre/atualiza/desinstala no CI; falta revisão visual na sua máquina |
| Atualizador, gerenciador de drivers | ⏳ etapas seguintes |
| Sincronização, licenciamento | ⏳ etapa 8 |

## Requisitos
- Python 3.12 (alvo: 3.12.16). O núcleo usa **somente a biblioteca padrão**.
- Guia para Windows: [docs/INSTALL-WINDOWS.md](docs/INSTALL-WINDOWS.md)

## Uso rápido
```bash
python -m venv .venv && .venv/bin/pip install -e .[dev]   # Windows: .venv\Scripts\...
nexus init --admin "SEU NOME"            # pede a senha do administrador (mín. 10 caracteres)
nexus --as "SEU NOME" status             # pede a senha; sem --as o acesso é anônimo (somente leitura)
nexus --as "SEU NOME" devices scan
nexus --as "SEU NOME" modules list
pytest
```
Os dados ficam em `%LOCALAPPDATA%\NexusOmnitech` (Windows) ou `~/.local/share/nexus-omnitech`; use `--home` ou `NEXUS_HOME` para mudar.

## Documentação
- [Arquitetura](docs/ARCHITECTURE.md)
- [Instalação, atualização e desinstalação](docs/INSTALACAO.md)
- [Interface WPF](ui/README.md)
- [Protocolo UI ↔ núcleo](docs/PROTOCOL.md)
- [Segurança e limitações conhecidas](docs/SECURITY.md)
- [Roadmap por etapas](docs/ROADMAP.md)

## Licença
Copyright © 2026 LMF Informática. Todos os direitos reservados. Veja [LICENSE](LICENSE).
