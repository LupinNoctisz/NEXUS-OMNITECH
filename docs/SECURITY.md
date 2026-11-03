# Segurança — o que está implementado e o que NÃO está

## Implementado (etapa 1)
- Operações destrutivas só executam com: permissão, confirmação explícita, **autorização registrada do proprietário**, backup concluído antes e registro de início/fim/falha (`core/safety.py`). Backup falhou ⇒ a operação não roda.
- Histórico de operações com hash encadeado; `nexus audit verify` detecta alteração/remoção no meio da cadeia.
- Logs e histórico redigem automaticamente campos com nome de senha/token/chave/credencial.
- Módulos: só carregam se registrados por admin, publicador confiável, manifesto idêntico ao fixado e arquivos íntegros; arquivos executáveis não declarados bloqueiam o módulo; caminhos fora da pasta do módulo são rejeitados.
- Backups verificados com checksum SHA-256 e `PRAGMA integrity_check`; restauração exige confirmação e cria antes um backup do estado atual.
- Nenhum segredo no código; `.gitignore` bloqueia `.env`, chaves e bancos locais.

## Limitações conhecidas (honestas)
1. **Identidade é declarativa.** Quem abre o núcleo informa o nome do técnico. Permissões evitam erro operacional, não protegem contra um usuário local mal-intencionado com acesso ao banco. Autenticação real vem na etapa 8.
2. **Publicador confiável ≠ assinatura.** O nome do publicador no manifesto pode ser escrito por qualquer um. A defesa atual é registro explícito + hash fixado. Assinatura criptográfica do manifesto (campo `signature` reservado) é requisito antes da distribuição de módulos.
3. **Cadeia de auditoria:** remover registros do FIM não é detectável localmente; a âncora online do último hash será feita na sincronização.
4. **Verificação de integridade tem janela TOCTOU** entre checar e importar o módulo; aceitável para validação interna, a revisar na etapa 9.
5. O provedor USB de **Windows (PowerShell/PnP) foi testado apenas com amostras de saída**, não em uma máquina Windows real.

## Princípios que guiam os próximos módulos
Não contornar proteções antirroubo ou de fabricantes, não acessar dados sem autorização do proprietário, não desabilitar mecanismos de segurança do Windows, usar apenas drivers/ferramentas de fontes oficiais.
