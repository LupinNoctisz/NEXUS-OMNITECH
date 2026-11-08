# Roadmap

Cada etapa só começa após a anterior estar testada e documentada. Antes de cada módulo: pesquisar protocolos, documentação oficial, licenças e limitações.

| # | Etapa | Situação |
|---|---|---|
| 1 | Arquitetura e núcleo | ✅ concluída (restam: atualizador, gerenciador de drivers) |
| 2 | Interface e navegação (tema escuro/claro, 8 seções iniciais, tela Início) | 🟡 compila e passa nos testes (CI Windows); falta revisão visual no Windows (as demais seções do projeto entram com seus módulos) |
| 3 | Diagnóstico de computadores (SMART, temperaturas, RAM, drivers, boot, integridade) | ⏳ |
| 4 | Ferramentas mobile (ADB, Fastboot, drivers; suporte por fabricante sem presumir protocolos iguais) | ⏳ |
| 5 | Consoles (PlayStation, Xbox, Nintendo — apenas o que cada fabricante permite) | ⏳ |
| 6 | Laboratório eletrônico (calculadoras, biblioteca, medições, datasheets) | ⏳ |
| 7 | Inteligência e relatórios (hipóteses ≠ defeitos confirmados; PDF) | ⏳ |
| 8 | Sincronização e licenciamento (Supabase, conflitos, tolerância offline, planos) | ⏳ |
| 9 | Segurança e testes (assinatura de módulos, revisão de TOCTOU, auditoria externa) | ⏳ |
| 10 | Preparação comercial | ⏳ |

**Nota de numeração:** as "Fases" do projeto (1 app desktop, 2 estabilidade, **3 biblioteca técnica**, 4 ferramentas, 5 diagnóstico inteligente, 6 instrumentos, 7 expansão, 8 ecossistema LMF) são mais recentes que a tabela acima; a Fase 3 está em projeto: ver [LIBRARY-DESIGN.md](LIBRARY-DESIGN.md). A tabela será alinhada na entrega 3.8.

Integração com o LMF Control: prevista como camada independente (importar equipamentos/OS, exportar laudos), sem acoplar os sistemas.
