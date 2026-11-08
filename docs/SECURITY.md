# Segurança — o que está implementado e o que NÃO está

## Implementado
**Identidade e acesso**
- Senha individual por técnico (scrypt, salt aleatório, parâmetros guardados no hash; mínimo de 10 caracteres, sem senhas só numéricas).
- Bloqueio temporário (5 min) após 5 falhas seguidas; mensagem única para usuário inexistente, senha errada ou conta bloqueada; tempo equalizado para usuário inexistente.
- A identidade do núcleo só muda por `login()`/`logout()`. Foram **removidos** o ator por variável de ambiente (`NEXUS_TECHNICIAN`) e por parâmetro do construtor. `NexusCore.actor` é somente leitura.
- Papéis `viewer` / `technician` / `admin`; técnico desconhecido, inativo ou sem senha não entra. Não é possível desativar o último administrador.
- Senhas nunca são gravadas nem registradas (log e histórico redigem campos de credencial); o hash nunca sai do repositório de técnicos (a API e as listagens expõem só `has_password`).
- Restaurar um backup revalida o técnico logado: se ele não existir no backup, a sessão é encerrada.

**Operações e dados**
- Operações destrutivas só executam com: permissão, confirmação explícita, **autorização registrada do proprietário**, backup concluído antes e registro de início/fim/falha (`core/safety.py`).
- Histórico com hash encadeado; `nexus audit verify` detecta alteração/remoção no meio da cadeia.
- Backups com checksum SHA-256 e `PRAGMA integrity_check`; restauração exige confirmação e cria antes um backup do estado atual. Pela API, backups são identificados **só pelo nome** (caminhos são rejeitados).

**Módulos**
- Só carregam se registrados por admin, publicador confiável, manifesto idêntico ao fixado e arquivos íntegros; executáveis não declarados e caminhos fora da pasta bloqueiam o módulo.
- O módulo recebe uma **fachada mínima** (`ModuleContext`): consulta de dispositivos, sessões (sujeitas às permissões do técnico), log, pasta de dados e registro de auditoria prefixado. Não recebe o núcleo, o banco, a trava de segurança nem os repositórios.

**Repositório** (ver [SECURITY.md](../SECURITY.md) na raiz e [DATA-POLICY.md](DATA-POLICY.md))
- `.gitignore` reforçado, `.env.example` fictício, scanner de segredos/dados pessoais no hook `pre-commit` e no CI, `CODEOWNERS`, Dependabot.

## Limitações conhecidas (honestas)
1. **Código no mesmo processo é confiável.** A autenticação protege a fronteira do processo (CLI e RPC). Um módulo carregado ou qualquer código Python no mesmo processo ainda pode, por reflexão, alcançar o estado interno. A fachada reduz acoplamento acidental, **não é um sandbox**; isolamento por processo está previsto para a etapa 9. Hoje a defesa é registro explícito por admin + hash fixado + publicador confiável.
2. **Publicador confiável ≠ assinatura.** O nome do publicador no manifesto pode ser escrito por qualquer um. Assinatura criptográfica do manifesto (campo `signature` reservado) é requisito antes de distribuir módulos.
3. **Contas legadas sem senha** (bancos criados antes da autenticação) podem ter a senha definida por qualquer pessoa com acesso local ao banco (`nexus technician set-password NOME`, operação auditada e sinalizada em `status`). Depois da primeira senha isso deixa de ser possível. Quem tem acesso físico/administrativo à máquina e ao arquivo do banco continua capaz de editá-lo diretamente.
4. **Quem tem acesso ao arquivo `nexus.db` pode editá-lo** (inclusive recalcular a cadeia de auditoria). A cadeia detecta adulteração parcial/acidental, não um adversário com acesso total ao disco. Remover registros do FIM não é detectável localmente; a âncora online do último hash será feita na sincronização.
5. **O bloqueio por falhas é por conta:** alguém pode bloquear temporariamente a conta de outro técnico errando a senha de propósito (troca segurança de senha por disponibilidade). Limitação aceita para uso local; revisar na etapa 9.
6. **Não há recuperação de senha por e-mail.** Um administrador redefine a senha de outro técnico; se o único administrador esquecer a senha, é preciso restaurar um backup ou intervir no banco.
7. Verificação de integridade de módulos tem janela TOCTOU entre checar e importar; a revisar na etapa 9.
8. O provedor USB de **Windows (PowerShell/PnP) foi testado apenas com amostras de saída**, não em uma máquina Windows real.

## Princípios que guiam os próximos módulos
Não contornar proteções antirroubo (FRP, iCloud etc.) ou de fabricantes, não acessar dados sem autorização do proprietário, não desabilitar mecanismos de segurança do Windows, usar apenas drivers/ferramentas de fontes oficiais.

## Quem pode ler o quê (Fase 2)

| Área | Leitor | Técnico | Administrador |
|---|---|---|---|
| Lista de técnicos | só nome, papel e situação | só nome, papel e situação | completa (bloqueios, senha definida, datas) |
| Segurança (`security.overview`) | bloqueado | bloqueado | total |
| Configurações e caminhos (`settings.get_all`, `system.paths`) | bloqueado | bloqueado | total |
| Trocar a própria senha ("Minha conta") | sim | sim | sim |

A recusa é feita no núcleo (permissões `security.read` e `settings.read`, só do administrador) e registrada na auditoria; a interface apenas esconde as telas. Quem não é administrador usa o tema escuro/claro só na sessão atual.

## Módulos: o arquivo de entrada (Fase 2)

O `entry` do manifesto deve ficar dentro da pasta do módulo (sem `..` nem caminho absoluto) e constar em `files` com seu SHA-256, para ser verificado antes de qualquer carregamento. Manifestos que não cumprem isso são ignorados (registrado no log).
