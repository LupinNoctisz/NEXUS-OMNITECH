# Instalação, atualização e desinstalação (Windows)

## O que é preciso
- Windows 10 ou 11 (64 bits).
- **Python 3.12 ou mais novo** já instalado (o NEXUS não empacota o Python). O .NET **não** é necessário: o instalador já inclui o que a interface precisa.
- Instalar o Python: `winget install Python.Python.3.12`, instalador do python.org ou `uv`.

## Instalar
1. Gere o instalador (ver "Gerar o instalador") ou baixe o artefato `NexusOmnitech-Setup-<versão>` da execução do CI e confira o `.sha256` ao lado.
2. Execute `NexusOmnitech-Setup-<versão>.exe`. Por padrão instala **só para o seu usuário** (não pede administrador) em `%LOCALAPPDATA%\Programs\NEXUS OMNITECH`.
3. Marque "Criar ícone na área de trabalho" se quiser. O atalho do menu Iniciar sempre é criado.
4. Abra pelo atalho. No **primeiro uso** o NEXUS pede para criar o administrador; depois disso, abre na tela de login.

Se o Python não for encontrado, o NEXUS explica o que foi verificado e oferece **escolher o `python.exe` manualmente** (também em Configurações). Versões abaixo de 3.12 e o atalho falso da Microsoft Store são recusados.

## Onde ficam os dados
| O quê | Onde |
|---|---|
| Banco, backups, logs, módulos instalados | `%LOCALAPPDATA%\NexusOmnitech` (ou a pasta em `NEXUS_HOME`) |
| Preferências da janela, tema inicial, caminho do Python | `%APPDATA%\NexusOmnitech\ui-settings.json` |
| Programa e núcleo | pasta de instalação (`core\`, `modules\`) |

Em **Configurações** o NEXUS mostra os caminhos reais em uso.

## Atualizar
Execute o instalador de uma versão mais nova por cima. O programa e o núcleo são substituídos (arquivos que saíram da versão nova não sobram); **banco, backups e configurações não são tocados**. Se a nova versão alterar o esquema do banco, o núcleo cria antes, sozinho, um backup verificado (`...-pre-migration-vN.db`) e recusa abrir um banco criado por versão mais nova (sem downgrade automático). Feche o NEXUS antes: o instalador avisa se estiver aberto.

## Desinstalar
Configurações do Windows → Aplicativos → NEXUS OMNITECH → Desinstalar. Ao final, o desinstalador pergunta se você quer **também apagar os dados** (padrão: Não). Em desinstalação silenciosa (`/VERYSILENT`) os dados **nunca** são apagados. Se usou `NEXUS_HOME` personalizado, essa pasta nunca é apagada pelo desinstalador.

## Gerar o instalador
Requer .NET 8 SDK e Inno Setup 6 (`winget install JRSoftware.InnoSetup`):
```powershell
./installer/build.ps1 -Version 0.1.0          # saída: build\installer\NexusOmnitech-Setup-0.1.0.exe (+ .sha256)
./installer/test-installer.ps1                # instala, abre, atualiza e desinstala de verdade (use numa máquina de teste)
```
O CI (`Interface (.NET/WPF)`) executa exatamente isso a cada alteração e publica o instalador como artefato do CI (não é uma release).

## Diagnóstico
- `NexusOmnitech.exe --selftest relatorio.json`: inicia o núcleo sem janela e grava Python usado, versões e resultado.
- Logs: `%LOCALAPPDATA%\NexusOmnitech\logs\` (`ui.log` da interface e logs do núcleo).

## Limitações conhecidas
- O instalador **não é assinado digitalmente**: o Windows SmartScreen pode avisar. Assinatura de código fica para a preparação comercial.
- Não há atualização automática online; atualizar é executar o novo instalador. A estrutura (versões compatíveis, backup antes de migrar) já existe.
- O instalador é auto-contido (inclui o runtime .NET, ~70 MB comprimido) para funcionar em máquinas sem .NET.
- Testado apenas em Windows Server do CI e no Linux (núcleo); **a aparência na sua máquina ainda precisa da sua revisão**.
