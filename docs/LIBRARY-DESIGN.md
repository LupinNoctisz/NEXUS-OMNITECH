# Biblioteca Técnica — auditoria e arquitetura (Fase 3.1)

**Situação: PROPOSTA para aprovação. Nenhum código da biblioteca foi escrito.** Base auditada: NEXUS OMNITECH 0.1.1
(`main`, CI verde). Este documento só muda quando o dono do projeto aprovar cada decisão listada na seção 9.

## 1. Estado atual (auditoria)

| Área | O que existe | Uso na biblioteca |
|---|---|---|
| Núcleo | Python 3.12, **somente biblioteca padrão** (`NexusCore`: banco, auditoria, backup, permissões, módulos, dispositivos, sessões) | A biblioteca entra como **serviço do núcleo** (`core/library.py`), como `devices` e `sessions`. Não é um módulo: outros módulos (diagnóstico, laboratório) a consultam |
| Banco | SQLite, `PRAGMA user_version`, migrações em `database.py` (v3 hoje), backup automático antes de migrar, FTS5 disponível | Migração **v4** aditiva (só `CREATE`), sem tocar nas tabelas atuais |
| Permissões | papéis viewer/technician/admin, `core.require(...)` no núcleo, recusas auditadas | Novas permissões `library.read/write/manage` |
| Auditoria | cadeia de hash; ações registradas por técnico | Cada inclusão/edição/remoção/verificação vira um registro |
| RPC | lista fechada de métodos, parâmetros tipados, 1 MiB por mensagem, sem caminhos de arquivo (backups são por nome) | Novos métodos `library.*`; **arquivos nunca passam pelo RPC** |
| Interface | WPF + MVVM (`Presentation` sem WPF, testável), 9 telas, tema claro/escuro, `NavItem.Requires` esconde telas por permissão | Nova tela "Biblioteca" no mesmo padrão |
| Arquivos | `Paths`: `logs`, `backups`, `modules`, `reports`, `module_data` | Nova pasta `library/` (arquivos e `inbox/`) |
| Dispositivos | `devices.vendor/model/serial` | Ligação "este equipamento → o que a biblioteca sabe" |
| Integridade de pacotes | módulos: manifesto + SHA-256 + publicador confiável | Mesmo padrão para futuros **pacotes de conteúdo** |
| Já existe biblioteca/gestão de documentos? | **Não.** Só o módulo planejado `nexus.electronics_lab` (datasheets), que passará a usar este serviço | — |

## 2. Limites e conflitos que condicionam o desenho

1. **Backup só cobre o banco.** Arquivos (PDF) ficam fora. Solução: arquivos em `library/files/` identificados por SHA-256; o banco guarda o índice; verificação de ausentes/órfãos; backup dos arquivos como etapa própria (decisão D5).
2. **RPC não aceita caminhos.** Importar documento = a interface copia para `library/inbox/`; o núcleo importa **pelo nome** (mesma regra dos backups).
3. **Servidor RPC de uma thread, mensagens de 1 MiB.** Importações têm limite de tamanho e hash em blocos; só metadados e textos curtos trafegam.
4. **Sem dependências externas no núcleo.** Sem leitura de texto de PDF/OCR (decisão D6). Indexam-se metadados, notas, artigos e TXT/Markdown.
5. **FTS5 depende do SQLite do Python do usuário.** Verificado no ambiente de desenvolvimento; o núcleo detecta em tempo de execução e cai para busca simples (normalizada) se faltar.
6. **Numeração.** No `ROADMAP.md` a "Etapa 3" é diagnóstico de PC; "Fase 3" aqui é a biblioteca. O roadmap será alinhado na entrega 3.8.
7. **Versão.** `VersionCompat` exige mesmo major.minor entre interface e núcleo; mudança de esquema justifica **0.2.0** (decisão D9), sempre com autorização.

## 3. Arquitetura proposta

```
 Tela Biblioteca (WPF)  ──RPC library.*──►  api/methods.py (lista fechada)
        │ copia arquivo p/ inbox                     │
        ▼                                            ▼
 <dados>/library/inbox/              core/library.py  (LibraryService)
                                       ├─ catálogo: categorias, fabricantes, famílias, modelos
                                       ├─ itens de conhecimento (+ revisões)
                                       ├─ documentos (armazenamento por SHA-256)
                                       ├─ busca (FTS5 + normalização + fallback)
                                       └─ verificação de integridade da biblioteca
 <dados>/library/files/ab/<sha256>   ◄── somente leitura depois de gravado
```

### 3.1 Modelo de dados (esboço da migração v4, sujeito à fase 3.2)

- `lib_categories(id, slug UNIQUE, name, parent_id, kind {equipment|component}, builtin, sort_order)` — as 9 categorias iniciais são **dados semeados**, não código; novas categorias = novas linhas.
- `lib_manufacturers(id, name UNIQUE NOCASE)`; `lib_manufacturer_aliases(manufacturer_id, alias)`.
- `lib_families(id, manufacturer_id, name)` — família/série.
- `lib_models(id, category_id, manufacturer_id, family_id, name, notes)`; `lib_model_codes(model_id, code, kind {pn|sku|mtm|...})` — código de produto pesquisável; `lib_model_aliases`.
- `lib_entries(id, kind, title, category_id, manufacturer_id, description, body, symptom, error_code, safety_warnings, source_name, source_url, published_at, added_at, added_by, updated_at, trust, trust_note, verified_by, verified_at, license_note, deleted_at)`
  - `kind`: `spec`, `service_manual`, `user_manual`, `diagram`, `error_code`, `diagnostic_procedure`, `maintenance_procedure`, `compatibility`, `bios_firmware`, `vendor_doc`, `note`.
  - `trust` (CHECK): `official_declared`, `third_party`, `manual`, `unverified` (padrão `unverified`).
- `lib_entry_models(entry_id, model_id)` — modelos compatíveis (N:N); `lib_entry_components(entry_id, category_id)` — componentes envolvidos; `lib_compat(model_id, component_model_id, relation, entry_id)` — compatibilidade **estruturada**, não texto livre.
- `lib_entry_revisions(entry_id, rev, changed_at, changed_by, snapshot)` — histórico de edições (confiabilidade e auditoria).
- `lib_documents(id, sha256 UNIQUE, size, mime, ext, original_name, stored_rel, added_at, added_by)`; `lib_entry_documents(entry_id, document_id, role)` — o mesmo arquivo não é guardado duas vezes (**sem duplicação**).
- `lib_fts` (FTS5) sobre título, descrição, corpo, sintoma, código de erro, nomes/códigos/aliases de modelos e fabricantes. Reindexação explícita dentro da mesma transação do serviço (testável), com opção de reconstruir.
- `lib_session_refs(session_id, entry_id)` — "consultado nesta sessão" (opcional, útil para o laudo).

Compatibilidade com o que existe: só tabelas novas; nada em `devices`, `sessions`, etc. muda. Antes da migração o núcleo já faz backup verificado.

### 3.2 Confiabilidade e fontes (sem inventar conteúdo)

- Quatro níveis visíveis (selo na lista e no detalhe): **Oficial (declarado)**, **Terceiros**, **Cadastrado manualmente**, **Não verificado**.
- O NEXUS **não consegue provar** que algo é oficial. Por isso o rótulo é "declarado oficial por *técnico* em *data*, fonte *X*", exige fonte (URL e/ou documento com hash) e só o administrador pode atribuí-lo. Nunca é o padrão.
- Todo item novo nasce **Não verificado**. Verificar/atribuir nível fica registrado (quem, quando, nota) e na auditoria.
- A biblioteca **nasce vazia** (apenas a estrutura de categorias). Nenhuma especificação, código de erro ou procedimento é embutido sem fonte. Dados de exemplo só em testes, claramente fictícios.
- Códigos de erro são **escopados por fabricante/família**: o mesmo código significa coisas diferentes em marcas diferentes.

### 3.3 Documentos: armazenamento e validação

Fluxo: interface copia para `inbox/` → `library.import(nome_na_inbox, ...)`.

1. **Nome da inbox** validado (lista restrita de caracteres), resolvido **dentro** da inbox; recusa links simbólicos/pontos de reanálise, arquivo que não seja regular, nomes reservados do Windows.
2. Abre **uma vez** e usa o mesmo handle para: ler assinatura (magic bytes), medir tamanho e calcular SHA-256 enquanto copia para um temporário (evita TOCTOU entre checar e usar).
3. **Tipos permitidos (proposta):** PDF (`%PDF-`), TXT/Markdown (UTF-8 válido, sem NUL), PNG, JPEG. **Recusados:** executáveis e scripts, SVG e HTML (podem conter script), Office com macros, arquivos compactados. A extensão nunca basta: vale o conteúdo.
4. **Limite de tamanho** configurável (proposta: 100 MiB por arquivo) e checagem de espaço em disco; falha limpa e sem arquivo parcial.
5. Grava em `library/files/<2 primeiros hex>/<sha256>` (nome **não controlado pelo usuário**); nome original fica só como metadado sanitizado. Se o hash já existe, reaproveita (dedupe) e apenas cria o vínculo.
6. Antes de **abrir** um documento, o núcleo reverifica o hash; se divergir, recusa e alerta. A interface abre no leitor do Windows (decisão D7); nada é executado.
7. **Remoção** exige permissão `library.manage` e confirmação; é *soft delete* do vínculo/entrada; o arquivo só sai do disco se nenhum item o referenciar e o administrador confirmar a limpeza. Tudo auditado.
8. Metadados e arquivo original ficam preservados; nenhum arquivo é alterado.

### 3.4 Pesquisa

- Normalização: minúsculas, sem acentos, símbolos unificados (`-`, `_`, espaços), códigos de produto comparados sem separadores.
- FTS5 (`unicode61 remove_diacritics`, prefixo) + tabela de **aliases** (ex.: nomes alternativos de modelo) → tolerância a variações de escrita.
- Sugestão "Você quis dizer…" por similaridade (`difflib`, biblioteca padrão) sobre nomes, aliases e códigos.
- Filtros combináveis: categoria, fabricante, família, modelo, tipo, confiabilidade; busca por sintoma e por código de erro.
- Contrato de indexação: `SearchIndex` com implementação FTS5 e fallback; outro mecanismo (ex.: texto de PDF) entra depois sem mudar a API.
- Meta de desempenho a validar em 3.7: resposta < 150 ms com 50 mil itens (será medida e informada, não presumida).

### 3.5 Offline e sincronização futura

Tudo é local; **nenhuma chamada de rede** na biblioteca. URL é só referência: exibida como texto e aberta no navegador apenas por clique do técnico (somente `http/https`). Atualização futura de conteúdo = **pacotes de conteúdo** com manifesto + SHA-256 + publicador confiável (mesmo padrão dos módulos), importados manualmente ou por um sincronizador opcional que nunca é requisito para consultar.

### 3.6 Permissões e auditoria

| Ação | Leitor | Técnico | Admin |
|---|---|---|---|
| Pesquisar e consultar itens/documentos | sim | sim | sim |
| Cadastrar/editar itens, importar documentos | não | sim | sim |
| Remover, marcar como verificado/oficial, gerenciar categorias, limpar arquivos | não | não | sim |

Permissões novas: `library.read`, `library.write`, `library.manage`. Recusa no núcleo (e auditada), a interface apenas esconde. Registrados na auditoria: inclusão, edição (com diff mínimo), remoção, mudança de confiabilidade, importação, falha de verificação. O conteúdo em si não vai para a auditoria (só identificadores e hashes).

### 3.7 Interface (fase 3.4)

Nova tela "Biblioteca" (`NavItem` com `Requires="library.read"`), mesma identidade visual: barra de pesquisa em destaque no topo; filtros em ComboBox (categoria, fabricante, tipo, confiabilidade) já estilizados no tema escuro; lista de resultados com selo de confiabilidade; painel de detalhe (campos do registro, modelos compatíveis, documentos com Abrir/Verificar). Conteúdo exibido como **texto simples** (Markdown não é renderizado como HTML). Nenhuma tela existente é alterada além do menu.

### 3.8 Diagnóstico (ligações previstas, sem implementar agora)

- A partir de um dispositivo (fabricante/modelo normalizados) → "ver na biblioteca".
- Sintoma/código de erro → procedimentos de diagnóstico relacionados.
- Procedimentos têm campo obrigatório de **avisos de segurança** (ESD, bateria, tensão da rede) e marcação de **risco/destrutivo**; quando destrutivo, o fluxo continua passando pelo `SafetyGuard` (confirmação, autorização do proprietário, backup, auditoria).
- Conteúdo da biblioteca descreve **hipóteses e procedimentos**, nunca defeitos confirmados.

## 4. Segurança — resumo dos controles

Sem caminhos arbitrários (inbox + nome validado + sem symlink); validação por conteúdo; limite de tamanho/espaço; hash e dedupe; nome em disco não controlado pelo usuário; reverificação do hash ao abrir; permissões no núcleo; auditoria; erros tratados sem traceback cru; sem rede; sem execução de conteúdo importado; Markdown/URL tratados como texto.

## 5. Backup e recuperação

- Tabelas `lib_*` entram no backup do banco como as demais (e na verificação de integridade).
- Comando/RPC `library.verify`: lista arquivos **ausentes** (banco aponta, disco não tem), **corrompidos** (hash não confere) e **órfãos** (disco tem, banco não). Nunca apaga sozinho.
- Restaurar um backup do banco com arquivos ausentes não falha: a biblioteca indica "arquivo ausente" por item.
- Backup dos arquivos (cópia verificada com manifesto) como entrega própria (D5).

## 6. Riscos

| Risco | Mitigação |
|---|---|
| Direitos autorais de manuais | Biblioteca nasce vazia; técnico importa o que pode usar; campo `license_note`; nada é baixado nem copiado de sites; conteúdo próprio da LMF só com autoria dela |
| Arquivo malicioso (PDF/imagem) abrindo no leitor externo | Validação por assinatura, tipos restritos, hash, aviso na primeira abertura, nunca executar; sem antivírus embutido (limitação declarada) |
| Dados de clientes em arquivos importados | Aviso na importação e atualização do `DATA-POLICY.md`: biblioteca é para documentação técnica, não para arquivos de clientes |
| Conteúdo errado tratado como oficial | Quatro níveis, padrão não verificado, atribuição restrita ao admin, rótulo "declarado" |
| Disco cheio / arquivos grandes | Limite, checagem de espaço, falha limpa, sem parciais |
| Servidor RPC de uma thread bloqueado por importação grande | Limite de tamanho, hash em blocos; avaliar fila em fase futura se necessário |
| Falta de FTS5 no Python do usuário | Detecção + fallback + aviso em Configurações |
| Biblioteca vazia parecer "quebrada" | Estado vazio explicativo na tela, sem dados fictícios |

## 7. Plano de entregas (subfases do prompt da Fase 3)

| Subfase | Entrega | Verificação | Precisa de autorização |
|---|---|---|---|
| 3.1 | Este documento | revisão do dono | aprovar decisões D1–D9 |
| 3.2 | Modelagem: migração v4, repositório, testes de migração (inclui v3→v4 com backup e rollback) | testes Python + CI | **sim — altera o banco** |
| 3.3 | Backend: serviço, permissões, auditoria, RPC, CLI, fixtures | testes de permissões, auditoria, erros | sim, por etapa |
| 3.4 | Interface: tela, busca, filtros, detalhe | testes de ViewModel + CI Windows; **sua revisão visual** | sua revisão |
| 3.5 | Documentos: inbox, validação, armazenamento, abrir/verificar/remover | testes de segurança (symlink, assinatura falsa, tamanho, dedupe, TOCTOU) | — |
| 3.6 | Pesquisa avançada: FTS5, aliases, sugestões, fallback | testes de relevância/tolerância e desempenho medido | — |
| 3.7 | Testes e validação: permissões, persistência, offline, desempenho, backup/restore | relatório com números reais | sua validação instalada |
| 3.8 | Documentação, histórico, alinhamento do roadmap, versão 0.2.0, instalador em **rascunho** | CI + instalação | **sim — versão e release** |

Cada entrega: pequenas alterações, testes rodados e resultados reais informados, sem desativar testes, sem mexer em funcionalidades existentes.

## 8. Itens essenciais que o prompt original não cobre (recomendados)

1. **Política de conteúdo sensível:** a biblioteca não deve hospedar nem indexar material para burlar bloqueios (senha de BIOS/Windows sem autorização do proprietário, antifurto, FRP/iCloud). Regra espelha as já adotadas no projeto. → D8.
2. **Dados pessoais em anexos** (ver riscos) e atualização do `DATA-POLICY.md`.
3. **Histórico de revisões** dos itens (quem mudou o quê), importante para confiança.
4. **Aviso de segurança obrigatório** em procedimentos de manutenção/diagnóstico e marcação de risco.
5. **Códigos de erro por fabricante/família** (mesmo código, significados distintos).
6. **Campos de BIOS/firmware** (versão, data, notas, risco de gravação) e **compatibilidade estruturada** entre componentes.
7. **Ligação com sessões** ("consultado nesta sessão") para compor laudos.
8. **Verificação de integridade da biblioteca** (ausentes, corrompidos, órfãos) e cota/limite de disco.
9. **Licença/origem por documento** e aviso de uso interno.
10. **Criptografia em repouso:** fora do escopo agora (o banco também não a tem); registrar como decisão futura.

## 9. Decisões necessárias

| # | Decisão | Proposta |
|---|---|---|
| D1 | Aprovar o desenho de tabelas e a migração v4 (altera o banco) | Aprovar na 3.2, com backup automático já existente |
| D2 | Remoção: *soft delete* com auditoria e limpeza de arquivo só por confirmação do admin | Sim |
| D3 | Formatos e tamanho máximo | PDF, TXT/MD, PNG, JPEG; 100 MiB; sem SVG/HTML/Office/compactados |
| D4 | Níveis de confiabilidade e quem atribui "oficial declarado" | Quatro níveis; só admin; exige fonte |
| D5 | Backup dos arquivos da biblioteca | Etapa própria (cópia verificada, separada do backup do banco) |
| D6 | Texto dentro de PDF/OCR | Adiado; avaliar custo/dependência depois |
| D7 | Abrir documentos | Leitor do Windows (sem visualizador embutido) nesta fase |
| D8 | Política de conteúdo sensível (item 8.1) | Adotar |
| D9 | Versão | 0.2.0 na entrega 3.8, com sua autorização |
