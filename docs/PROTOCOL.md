# Protocolo UI ↔ NEXUS CORE (v1.0)

A interface (WPF) inicia o núcleo como **processo filho**: `python -m nexus --home <pasta> serve --stdio`
(ou `nexus serve --stdio`). Não existe porta de rede: o único cliente possível é quem criou o processo.

## Transporte
- JSON-RPC 2.0, **uma mensagem JSON por linha** (`\n`), UTF-8 na entrada; as respostas saem em **ASCII puro** (acentos como `\uXXXX`), o que evita problemas de codificação no Windows.
- Somente `stdout` carrega o protocolo (qualquer `print` acidental é desviado para `stderr`). Logs vão para o arquivo de log do NEXUS.
- Limite de 1 MiB por mensagem. Lotes (arrays) não são suportados. Chamadas sem `id` são executadas sem resposta.
- O servidor processa **uma requisição por vez**; a UI deve chamar de forma assíncrona e aplicar timeout.
- EOF na entrada ou `rpc.shutdown` encerra o servidor.

## Segurança
- **Lista fechada de métodos** (tabela abaixo). Não há método genérico, nem execução de comandos, nem caminhos de arquivo livres.
- Parâmetros não declarados, de tipo errado, fora da lista de valores permitidos ou grandes demais são rejeitados (`-32602`).
- Tudo exceto `rpc.hello`, `rpc.shutdown` e `auth.*` exige login (`-32002`). As **permissões do técnico logado** continuam sendo aplicadas pelo núcleo (`-32001`).
- Backups são referenciados **pelo nome** devolvido em `backups.list`; nomes com caminho são rejeitados (`-32006`).
- Senhas não são registradas em log nem no histórico. Erros internos devolvem mensagem genérica; o detalhe fica só no log.
- Se `backups.restore` remover o técnico logado (ele não existe no backup), a resposta traz `session_active: false` e a próxima chamada exigirá novo login.

## Códigos de erro
| Código | Significado |
|---|---|
| -32700 / -32600 / -32601 / -32602 / -32603 | JSON inválido / requisição inválida / método desconhecido / parâmetros inválidos / erro interno |
| -32000 | Erro de negócio (ex.: sessão já aberta) |
| -32001 | Permissão negada |
| -32002 | Não autenticado ou credenciais inválidas/conta bloqueada |
| -32003 | Confirmação obrigatória (`confirmed: true`) |
| -32004 | Falha de integridade (módulo) |
| -32005 | Erro de módulo |
| -32006 | Erro de backup |
| -32007 | Validação (ex.: senha fraca, valor de configuração inválido) |

`error.data.type` traz o nome do tipo do erro.

## Métodos
| Método | Login | Parâmetros | Resultado |
|---|---|---|---|
| `rpc.hello` | não | – | `protocol`, `core_version`, `schema_version`, `methods`, `actor`, `role`, `permissions`, `authenticated` |
| `rpc.shutdown` | não | – | `{ok}` |
| `setup.status` | não | – | `{initialized}` (false = primeiro uso, ainda não há técnicos) |
| `setup.create_admin` | não | `name`, `password` | `actor`, `role`, `permissions` — cria o PRIMEIRO administrador e entra; o núcleo recusa se já existir qualquer técnico |
| `system.paths` | sim | – | `home`, `database`, `logs`, `backups`, `modules` |
| `auth.login` | não | `name`, `password` | `actor`, `role`, `permissions` |
| `auth.logout` / `auth.whoami` | não | – | |
| `auth.change_password` | sim | `old_password`, `new_password` | `{changed}` |
| `status.get` | sim | – | painel inicial (dispositivos, sessões, operações, módulos, backups, sync, alertas) |
| `security.overview` | sim | – | permissões, integridade do banco e do histórico, técnicos, módulos |
| `devices.list` | sim | `connection?` | lista |
| `devices.scan` | sim | – | `{found, errors}` |
| `devices.add` | sim | `kind`, `vendor?`, `model?`, `serial?`, `label?` | `{id}` |
| `devices.identify` | sim | `text` (até 2000) | `{kind, vendor, model, serial, sources, alternatives, warnings}` — só sugere (não grava); exige `devices.manage`; valores de preenchimento ("To be filled by O.E.M.", "0000") são descartados e vários seriais nunca são adivinhados |
| `sessions.recent` / `sessions.open` | sim | `limit?` | lista |
| `sessions.start` | sim | `device_id`, `kind?` | `{id}` |
| `sessions.finish` | sim | `id`, `status?`, `summary?` | `{ok}` |
| `audit.list` | sim | `limit?`, `session_id?` | lista |
| `audit.verify` | sim | – | `{ok, records, first_bad_id, scope}` (`scope`: `full`; a conferência completa percorre a cadeia em lotes) |
| `modules.list` | sim | – | estado real de cada módulo |
| `modules.verify` | sim | `id` | `{ok, problems}` |
| `modules.register` | sim | `id`, `confirmed` | `{ok}` |
| `modules.enable` / `modules.disable` | sim | `id` | `{ok}` |
| `backups.list` | sim | – | `name`, `size_bytes`, `modified_utc`, `has_checksum` |
| `backups.create` | sim | `reason?` | `{name}` |
| `backups.verify` | sim | `name` | `{ok}` |
| `backups.restore` | sim | `name`, `confirmed` | `{safety_backup, session_active}` |
| `settings.get_all` / `settings.set` | sim | `key`, `value` | |
| `technicians.list` | sim | – | sem hash de senha (`has_password`) |
| `technicians.add` | sim | `name`, `role`, `password` | `{id}` |
| `technicians.set_active` | sim | `name`, `active` | `{ok}` |
| `technicians.set_password` | sim | `name`, `new_password` | `{changed}` (redefinição por admin) |

Datas e horas vêm em **UTC** (ISO 8601); a interface converte para o horário local.

## Fora desta versão
Operações destrutivas (`SafetyGuard`) **não** são expostas: ainda não existe nenhuma ação destrutiva real. Quando
um módulo trouxer uma, ela entrará como método próprio, com confirmação, autorização do proprietário e backup.
