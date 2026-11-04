# Arquitetura — NEXUS CORE (etapa 1)

## Decisão de stack (híbrida)
- **Núcleo, banco e motor de módulos: Python 3.12, somente biblioteca padrão.** Justificativa: permite testar a lógica
  (integridade, permissões, auditoria, backups) em qualquer sistema e entregar uma base verificável antes da interface.
- **Interface desktop: C#/.NET 8 com WPF (MVVM)**, falando com o núcleo por JSON-RPC sobre stdio com processo filho (sem porta de rede).
  Contrato em [PROTOCOL.md](PROTOCOL.md). O núcleo continua em Python; o empacotamento do Python fica para depois.
- **C/C++ e PowerShell** entram nos módulos que precisarem de hardware ou automação do Windows.
- **Supabase** (ou equivalente) apenas na etapa 8 (sincronização/licenciamento). O núcleo funciona 100% offline.

## Camadas
```
 UI WPF ──(stdio JSON-RPC, ver PROTOCOL.md)──► nexus.api (lista fechada de métodos)
 CLI (nexus)  ─────────────────────────────────►  NexusCore (fachada)
                    ├─ Database (SQLite, migrações, backup API)
                    ├─ AuditLog (hash encadeado)      ├─ SettingsStore
                    ├─ Permissions / Technicians      ├─ BackupManager
                    ├─ DeviceRegistry + Providers     ├─ SessionManager
                    ├─ SafetyGuard (destrutivas)      └─ ModuleRegistry
 Módulos (nexus.*) ◄── ModuleContext (superfície mínima: logger, devices, sessions, audit, data_dir)
```

## Módulos
Cada módulo é uma pasta com `manifest.json` (id, versão, publicador, `entry`, `min_core`, `files` com SHA-256).
Estados: `planned` (apenas declarado) e `available`. Fluxo: `seal` (desenvolvedor) → `register --confirm` (admin) →
`enable` → carregamento no início do núcleo, **com nova verificação de integridade a cada carga**.
Módulos podem ser instalados, atualizados, ativados e desativados de forma independente.

## Dados
SQLite com `user_version` e migrações em `database.py`. Tabelas: settings, technicians, devices, sessions, modules, operations.
Dados de diagnóstico/medições entram nas etapas dos respectivos módulos, via novas migrações.

## Regras de produto aplicadas
- Nenhum dado fictício: `devices scan` grava apenas o que o sistema realmente informa.
- Provedores de dispositivos são plugáveis; falha de um não derruba os demais.
- `status` calcula alertas a partir de verificações reais (integridade do banco, da cadeia de auditoria e dos módulos, backups antigos, sessões esquecidas).

## Identidade
Autenticação por senha individual (scrypt) em `core/auth.py`. O ator do núcleo é somente leitura e só muda por `login()`/`logout()`.
Na UI, o login acontece por `auth.login` e vale para aquele processo do núcleo. Detalhes e limites em [SECURITY.md](SECURITY.md).
