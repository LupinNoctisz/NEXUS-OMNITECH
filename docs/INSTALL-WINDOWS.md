# Instalação no Windows — Python 3.12.16 + NEXUS

O Python 3.12.16 (25/10/2026) é uma versão **somente de segurança, distribuída só como código-fonte**: o python.org não
publica instalador `.exe` para ela (o último instalador oficial do 3.12 foi o 3.12.10). Por isso o caminho recomendado é o `uv`.

> Estes comandos **não foram executados em Windows** por quem os escreveu; o ambiente de desenvolvimento era Linux.

## 1. Instalar o uv e o Python 3.12.16 (PowerShell)
```powershell
winget install --id=astral-sh.uv -e
uv self update
uv python install 3.12.16
uv python list | Select-String 3.12.16
```
Se `3.12.16` não aparecer, atualize o uv de novo (`uv self update`). Enquanto o seu uv não listar a versão, use
`uv python install 3.12` (instala a mais recente que ele conhecer) — o projeto exige apenas `>=3.12`.

## 2. Instalar o NEXUS
```powershell
git clone https://github.com/LupinNoctisz/NEXUS-OMNITECH.git
cd NEXUS-OMNITECH
uv venv --python 3.12.16
.venv\Scripts\activate
uv pip install -e ".[dev]"
pytest
nexus init --admin "SEU NOME"
nexus --as "SEU NOME" status
```
Dados locais: `%LOCALAPPDATA%\NexusOmnitech`.

## Alternativas
- **Compilar do código-fonte oficial** (tarball + checksum em python.org/downloads/release/python-31216): trabalhoso no Windows.
- **Instalador oficial 3.12.10**: sem compilar; difere da 3.12.16 apenas nas correções de segurança.
