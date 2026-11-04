# Interface do NEXUS OMNITECH (C# / .NET 8 / WPF)

A interface **não calcula nem inventa nada**: toda informação exibida vem do núcleo Python por JSON-RPC
([protocolo](../docs/PROTOCOL.md)). Ela inicia o núcleo como **processo filho** (`python -m nexus serve --stdio`),
sem porta de rede, e não executa comandos do sistema.

> **Estado honesto:** o código foi escrito sem compilador .NET local; quem o compila e testa é o workflow
> `.github/workflows/dotnet.yml` (Windows), que passou (build + 64 testes, incluindo ponta a ponta com o núcleo real).
> **Ninguém ainda abriu a janela:** erros de layout/XAML em tempo de execução, cores e usabilidade só aparecem no seu teste.

## Projetos
| Projeto | Papel |
|---|---|
| `Nexus.CoreClient` | Transporte (processo filho), JSON-RPC 2.0, API tipada (`ICoreApi`) e DTOs que espelham o JSON do núcleo |
| `Nexus.Presentation` | ViewModels (MVVM, CommunityToolkit.Mvvm) **sem dependência de WPF**, logo testáveis |
| `Nexus.App` | WPF: janela, login, 8 telas (Início, Dispositivos, Diagnósticos, Histórico, Módulos, Backups, Segurança, Configurações), temas escuro/claro |
| `Nexus.Tests` | xunit: contrato com respostas reais do núcleo (`Fixtures/`), JSON-RPC, ViewModels e um teste **ponta a ponta com o núcleo real** |

## Executar no Windows
Requisitos: .NET 8 SDK e Python 3.12 (o núcleo usa só a biblioteca padrão).
```powershell
dotnet build ui/Nexus.sln
dotnet test ui/Nexus.Tests
dotnet run --project ui/Nexus.App
```
Antes do primeiro uso crie o administrador: `python -m nexus init --admin "SEU NOME"` (com `PYTHONPATH=src`
ou depois de `pip install -e .`). Variáveis opcionais:

| Variável | Significado |
|---|---|
| `NEXUS_PYTHON` | executável do Python (padrão `python`) |
| `NEXUS_CORE_PATH` | pasta que contém o pacote `nexus` (ex.: `...\src`); se vazio, é procurada subindo a partir do executável |
| `NEXUS_HOME` | pasta de dados (banco, logs, backups) |

## Contrato e fixtures
`Nexus.Tests/Fixtures/*.json` são respostas reais do servidor com dados **fictícios**, geradas por
`python scripts/dump_rpc_fixtures.py`. Se o protocolo mudar, rode o script de novo e ajuste os DTOs.

## Limitações conhecidas
- ComboBox usa o estilo padrão do WPF (no tema escuro aparece claro).
- Os módulos de diagnóstico ainda não existem: a tela Diagnósticos diz isso e só gerencia sessões de atendimento.
- Idioma fixo em português do Brasil; sem instalador/empacotamento.
