# Shotwise

Captura de tela com anotações para Windows, inspirada no Shottr e no CleanShot X.
Roda na bandeja do sistema, responde a atalhos globais e abre um editor para anotar e esconder informações antes de copiar ou salvar.

## Mudança de nome (ShotWin → Shotwise)

A partir da versão 1.8 o programa se chama **Shotwise**. Ao abrir pela primeira vez, a pasta `%APPDATA%\ShotWin` (configurações, biblioteca e logs) é movida para `%APPDATA%\Shotwise`. A pasta de capturas que você escolheu continua a mesma; só quem nunca mudou o padrão passa a ter `Documentos\Shotwise` em instalações novas. O instalador fecha o ShotWin antigo, apaga as entradas antigas do Windows ("Abrir com", menu de contexto e inicialização) e cria as novas. Os projetos continuam com a extensão `.shotwin` e abrem normalmente.

## O que faz

| Recurso | Como |
|---|---|
| Tela inteira (monitor sob o cursor) | `Shift+Print Screen` |
| Área selecionada (tela congelada, com tamanho em pixels) | `Print Screen` |
| Repetir a última área | `Alt+Shift+R` |
| Janela ativa | `Alt+Shift+J` |
| Captura com rolagem (páginas longas, chats, logs, consoles web) | `Alt+Shift+S` |
| Repetir a última área capturada (mesmo monitor, mesmas coordenadas, mesmo modo: área ou rolagem) | `Alt+Shift+R` |
| Copiar o texto de uma área (OCR) | `Alt+Shift+T` |
| Gravar um GIF da área (aperte de novo para parar) | `Alt+Shift+G` |
| Gravar um vídeo MP4 da área (aperte de novo para parar) | `Alt+Shift+V` |
| Anotações | seta, linha, retângulo, elipse, marca-texto, caneta, texto, marcador numerado |
| Esconder informações | tarja sólida, pixelar, desfocar |
| Barra superior (só ícones) | Desfazer, Refazer · Copiar, Fixar (`Ctrl+F`), Salvar (fecha o editor), Salvar como · Inserir imagem · Capturas recentes · Configurações |
| Barra lateral | seleção, seta, linha, retângulo, elipse, marca-texto, caneta, texto, marcador · pixelar, desfocar, tarja · recortar, **redimensionar**, **fundo**, **OCR** |
| Retângulo e elipse | contorno apenas (padrão) ou preenchimento com cor (opção "Preenchimento", aceita transparência) |
| Camada ativa | o item que você clica vai para a frente. Se um texto cobre uma seta, clique sobre o traço da seta para selecioná-la |
| Texto | fundo transparente (padrão) ou colorido (opção "Fundo do texto", com cor e transparência) |
| Recortar | recorte não destrutivo: dá para remover o recorte depois |
| Mais de uma captura na mesma imagem | botão de inserir imagem: nova captura de área, colar (`Ctrl+V`), arquivo ou arrastar e soltar. Mova e redimensione cada imagem (Shift = proporção livre) |
| Fundo | ferramenta **Fundo**: painel de opções à direita com degradês prontos, estilo (Linear, Radial, Desfoque, **Mesclado**), Cor 1/Cor 2 (inverter), margem, cantos da imagem e do fundo, sombra (tamanho e direção), fundo transparente e **cor sólida**. Também dá para arrastar as bordas da moldura na imagem para mudar a margem |
| Painel de opções | painel translúcido de cantos arredondados, à direita da imagem (que é espremida para caber na área restante). Todos os ajustes seguem o mesmo desenho: título, valor à direita e barra embaixo. Aparece quando a ferramenta (ou o item selecionado) tem opções; Recortar e OCR mostram só um balão de dica. Arraste pelos três pontinhos para mover |
| Tarja sólida | cor (com conta-gotas), borda e espessura da borda; sempre opaca (não reversível) |
| Redimensionar | barra de escala, tamanho exato, girar 90°/180° e espelhar na horizontal/vertical |
| Desenhar várias formas | ao terminar uma forma ela fica selecionada; arrastar em outro lugar cria outra do mesmo tipo; clicar sobre um desenho do mesmo tipo o seleciona; clicar sobre outro tipo de desenho o seleciona e troca para a ferramenta dele |
| Opções lembradas | o editor guarda a última cor, espessura, fonte, intensidade, marcador, lupa, preenchimento, configuração do fundo e a posição do painel, e as aplica na próxima captura |
| Conta-gotas | botão **Cor** > Conta-gotas: clique na imagem para pegar a cor (ex.: tarja da mesma cor do fundo) |
| Redimensionar | ferramenta **Redimensionar**: arraste as alças da moldura (mantém a proporção; `Shift` estica livremente). "Tamanho exato…" aceita largura, altura ou percentual |
| Pixelar e desfocar | intensidade com `−`, controle deslizante e `+` (8 a 64; abaixo de 8 o texto pode ser reconstruído) |
| Reconhecer texto (OCR) | ferramenta **OCR** (`O`): arraste sobre o texto, revise e copie. Usa o OCR do Windows, offline |
| Depois da captura | Configurações: Abrir Editor, Copiar Imagem, Salvar Imagem ou Mostrar Miniatura (no canto) |
| Formato ao salvar | Configurações: PNG ou JPG |
| Ponteiro do mouse | Configurações: incluir o ponteiro na captura (tela inteira, área e janela) |
| Ao fechar o editor (`Esc`) | Configurações: copiar ou salvar a imagem. `Esc` primeiro tira a seleção ou a ferramenta; no próximo fecha o editor com a ação escolhida |
| Janela do editor | Configurações: sempre à frente; barra de ferramentas à esquerda, à direita ou em cima |
| Lupa (`Z`) | arraste sobre a parte a ampliar (elipse; `Shift` = círculo); a lupa aparece ao lado, arraste-a para onde quiser. As alças da origem redimensionam como na elipse; as alças da lupa mudam o tamanho e o aumento (o controle "Aumento" acompanha). A ampliação inclui tarjas e pixelados (não revela o que foi escondido) |
| Ajustar e anotar a área antes de capturar (Configurações > Captura) | depois de arrastar, use as alças ou mova; `Enter` ou clique duplo confirma, `Ctrl+C` confirma e copia, `Ctrl+S` confirma e salva (com as anotações aplicadas), `Esc` cancela. Uma barra junto da área oferece seta, retângulo, elipse, linha, caneta, texto, destaque e tarja, com botão de cor (abre a caixa de cores do Windows) e Desfazer (`Ctrl+Z`). A seta de seleção da barra ajusta a área e, depois de anotar, seleciona e move as anotações. Ao confirmar, as anotações seguem para o editor ainda editáveis (ou já aplicadas na imagem, se a ação for copiar/salvar). Com anotações feitas a área fica travada; desfaça para ajustá-la de novo |
| Fixar na tela | pelo botão da barra do editor (`Ctrl+F`) ou da miniatura. Arraste para mover, arraste as bordas para redimensionar, roda do mouse para zoom, `Ctrl`+roda para opacidade. Com o mouse em cima aparecem copiar, salvar, editar e fechar; qualquer ação fecha a fixação |
| Reabrir e continuar editando | biblioteca local (ícone de grade ou bandeja > Capturas recentes) |
| Desfazer/refazer | `Ctrl+Z` / `Ctrl+Y` (cobre desenhar, mover, redimensionar, recortar e mudar estilo) |
| Copiar / salvar | `Ctrl+C` / `Ctrl+S` / `Ctrl+Shift+S` / `Ctrl+Enter` (copia e fecha). Barra de ícones: passe o mouse para ver o nome e o atalho |

Os atalhos globais ficam em um menu separado (**Atalhos de teclado**, em Configurações > Geral) e podem ser trocados lá. Se o `Print Screen` abrir a Ferramenta de Captura do Windows, desligue essa opção em Configurações > Acessibilidade > Teclado.

## Instalação

Requisitos: Windows 10/11 e Python 3.11 ou superior no PATH.

**Rodar direto do código-fonte**

```
run.bat
```

Na primeira execução ele cria um ambiente virtual e instala as dependências (PySide6 e numpy).

**Gravação de GIF**: escolha a área, grave e pare pela barra ou pelo mesmo atalho. A janela de revisão tem linha do tempo e botões só com ícones (o nome aparece ao parar o mouse). O cursor vermelho anda pelo tempo (inclusive dentro de um quadro parado, como o começo da gravação): clique em qualquer ponto da linha para ir até lá e reproduzir dali. **Dividir** (`S`, ao lado do botão Excluir) corta o vídeo na posição do cursor ou num tempo digitado em *Dividir em*; cada pedaço vira um segmento, e clicar nele o seleciona. **Excluir** (`Del`) remove o segmento selecionado e **junta o que sobrou** num trecho só, pronto para tocar; para tirar um trecho do meio, divida nas duas pontas e exclua o do meio. O botão **Unificar** (ao lado de Dividir) junta todos os blocos que restaram num só. Também há Manter só o segmento (a faixa também pode ser ajustada arrastando as pontas ou digitando De/até), Desfazer (`Ctrl+Z`), Início, Reproduzir/Pausar (`Espaço`), Parar e girar ⟲/⟳. O botão Salvar grava o resultado em `Documentos\Shotwise`, copiando o arquivo para colar em e-mail ou chat. Quadros repetidos viram um só (arquivo menor). **Efeitos para tutorial**: escolha a ferramenta (Zoom, Destacar, Ocultar, Texto; o cursor vira cruz) e arraste sobre a prévia para marcar a área, e o efeito é criado na hora (a ferramenta continua ativa para criar outros; clique no botão de novo para desligar). O botão **Recortar**, separado dos demais, corta todo o vídeo para a área marcada. Detalhes: Zoom na área (aproxima durante o segmento selecionado e volta ao normal no fim), Destacar a área (escurece o resto), Ocultar a área (pixeliza), **Texto na área** (escreve um texto na área marcada) ou Recortar à área (todos os quadros). Efeitos do mesmo trecho podem ser empilhados (ex.: ocultar um item, destacar outro e escrever um texto entre 5 s e 10 s); cada um ocupa uma linha na faixa de efeitos. O player começa parado e toca o vídeo inteiro ao clicar em Reproduzir (caixa **Repetir** para recomeçar sozinho), mostrando os efeitos de cada bloco; a seleção serve só para editar. Zoom, destaque e ocultar viram **faixas na linha de efeitos** (abaixo da linha do tempo): dá para ter vários, em momentos e áreas diferentes; clique numa faixa para selecioná-la e arraste na imagem para mudar a área, arraste as pontas da faixa para mudar o tempo, ou remova (`Del`). Clicar num espaço vazio da faixa deseleciona, e o próximo efeito é novo. Os efeitos seguem o vídeo ao dividir/excluir trechos. Tudo tem Desfazer. Ao salvar, uma janela mostra o caminho e o botão **Mostrar na pasta** (a notificação da bandeja também abre a pasta ao clicar). O ponteiro do mouse sai ampliado, com halo amarelo e anel ao clicar (desligue em *Configurações*). Em *Configurações* ficam a fluidez (quadros por segundo), a duração máxima e a largura máxima. Usa o Pillow (já no `requirements.txt`).

**OCR (opcional)**: usa o Windows.Media.Ocr, que roda no próprio computador, sem rede. Os pacotes `winrt-*` estão em `requirements-ocr.txt` (o `run.bat` e os scripts de build instalam sozinhos; se falhar, só o OCR fica indisponível). O idioma reconhecido depende dos pacotes de OCR do Windows (Configurações > Hora e idioma > Idioma e região > Opções de idioma > Reconhecimento óptico de caracteres). Tente português e inglês.

**Gerar o instalador (recomendado): `build_installer.bat`**

Requisitos extras: [Inno Setup 6](https://jrsoftware.org/isdl.php) (`winget install --id JRSoftware.InnoSetup -e`).
O script gera o aplicativo com o PyInstaller e o instalador `dist_installer\Shotwise-Setup-<versão>.exe`.

- Instala só para o usuário atual, sem precisar de administrador (`%LOCALAPPDATA%\Programs\Shotwise`). No diálogo inicial dá para escolher "todos os usuários".
- **Atualizar**: aumente `__version__` em `shotwise/__init__.py`, rode `build_installer.bat` de novo e execute o novo instalador sobre o antigo. Ele pede ao Shotwise que se encerre sozinho (e, se não obedecer, fecha o `Shotwise.exe`), troca os arquivos e preserva configurações, capturas editáveis e a escolha de iniciar com o Windows. O `AppId` do `installer\Shotwise.iss` não pode mudar.
- **Desinstalar**: pelo Windows (Aplicativos instalados). Ele pergunta se deve apagar também `%APPDATA%\Shotwise` (configurações e capturas editáveis). Os PNGs salvos nunca são apagados.
- **Assinatura**: defina `SHOTWIN_SIGN_THUMBPRINT` com a impressão digital de um certificado de assinatura de código e o script assina o `.exe` e o instalador com o `signtool`. Sem assinatura, o Controle de Aplicativo Inteligente e o SmartScreen podem bloquear.
- Instalação silenciosa (para scripts): `Shotwise-Setup-1.24.0.exe /VERYSILENT /SUPPRESSMSGBOXES`.
- Se precisar de `.msi` (Intune/GPO), dá para gerar com o WiX a partir da mesma pasta `dist\Shotwise`.

**Gerar um executável único (`dist\Shotwise.exe`)**

```
build.bat
```

O executável fica em `dist\Shotwise.exe`. Pode copiar para qualquer pasta ou ativar "Iniciar com o Windows" nas configurações.

## Uso rápido

1. Pressione o atalho. Para área e rolagem, arraste o retângulo na tela. `Esc` ou botão direito cancela.
2. Conforme **Depois da captura**, o editor abre, a imagem é copiada, salva ou a miniatura aparece. Copiar e Salvar usam a captura **original** (sem tarjas): para dados sensíveis, use Abrir Editor e copie ao final.
3. Atalhos de ferramenta no editor: `V` selecionar, `A` seta, `L` linha, `R` retângulo, `E` elipse, `H` marca-texto, `P` caneta, `T` texto, `N` marcador numerado, `X` pixelar, `B` desfocar, `K` tarja, `Z` lupa, `C` recortar.
4. `Shift` ao desenhar trava em 45° (linhas e setas) ou em quadrado (formas).
5. `Ctrl` + roda do mouse dá zoom; botão do meio arrasta a imagem; `Delete` remove o item selecionado.
6. Clique duplo em um texto para editá-lo. Itens selecionados têm alças para redimensionar.

### Captura com rolagem

1. Deixe a página no ponto onde quer começar (normalmente o topo).
2. Pressione `Alt+Shift+S` e selecione **somente a área que rola** (sem a barra de abas, sem a barra de título). Cabeçalhos e rodapés fixos dentro da seleção são detectados e aparecem uma única vez.
3. O Shotwise posiciona o cursor no centro da seleção, gira a roda do mouse, captura e costura os quadros. `Esc` interrompe e mantém o que já foi capturado.
4. Termina sozinho quando a página não rola mais.

Limitações conhecidas: conteúdo animado ou com vídeo na área pode impedir o alinhamento (o app avisa e mantém o que montou até ali); a altura máxima padrão é 30.000 px.

## Esconder informações com segurança

| Ferramenta | Segurança |
|---|---|
| **Tarja sólida** (`K`) | Substitui os pixels por uma cor opaca. Não há como recuperar o conteúdo. Use para senhas, tokens, chaves, IPs, e-mails e dados de clientes. |
| **Pixelar** (`X`) | Com intensidade alta (16 ou mais) destrói o texto. Em intensidade baixa pode ser reconstruído por ferramentas de de-pixelização. |
| **Desfocar** (`B`) | Mais "bonito", porém o menos seguro dos três para texto pequeno. |

A imagem exportada é achatada: os pixels cobertos não existem mais no arquivo salvo nem no que vai para a área de transferência. Ainda assim, **o arquivo original da captura não é guardado**; o Shotwise só grava o resultado final.

Boa prática: antes de compartilhar um print com dados sensíveis, abra o PNG salvo e confira se nada ficou à mostra (inclusive em barras de título, abas do navegador e notificações).

## Segurança e privacidade

- **Sem rede.** O Shotwise não faz nenhuma conexão, não envia telemetria e não usa `eval`, `subprocess` nem `pickle`. A única rede usada é a do `pip` durante a instalação.
- **Área de transferência.** Ao copiar, a imagem é marcada para ficar fora do histórico do Windows (Win+V) e da sincronização na nuvem. Isso depende do Windows respeitar as marcas; confira no seu ambiente copiando um print e abrindo Win+V.
- **Captura original.** Com o editor ativado, ela só existe em memória até você copiar ou salvar o resultado final.
- **Capturas editáveis (biblioteca).** Para poder reabrir e continuar editando, o Shotwise guarda em `%APPDATA%\Shotwise\library` um arquivo `.shotwin` com a **imagem original, sem as tarjas aplicadas**, mais as anotações. O PNG exportado continua achatado e seguro, mas esse arquivo da biblioteca não. Por isso: ele fica só na pasta do seu usuário (nunca na pasta de capturas nem na nuvem do OneDrive por padrão), tem limite de itens (padrão 50, os mais antigos saem), pode ser excluído individualmente ou todo de uma vez, e pode ser desligado em Configurações ("Guardar capturas editáveis"). O arquivo é lido com validação (somente JSON e PNG, lista fixa de nomes, limites de tamanho e de quantidade; sem `pickle`). Não envie arquivos `.shotwin` a terceiros.
- **Miniatura no canto.** No modo "miniatura" a captura ainda não passou pelas tarjas: Copiar, Salvar e Fixar usam a imagem original. Para dados sensíveis, use "Editar" primeiro.
- **OCR.** O texto reconhecido é copiado fora do histórico do Windows (Win+V) e a imagem não sai do computador. O OCR é feito sobre a imagem já com as tarjas, então texto escondido não é reconhecido.
- **Modo sem editor** (salvar direto) (Configurações): a captura sem tratamento é salva em disco e, se marcado, copiada. Use apenas para telas sem dados sensíveis.
- **Pasta de capturas.** O padrão (`Documents\Shotwise`) pode estar dentro do backup do OneDrive. Para dados sensíveis, escolha outra pasta em Configurações.
- **Pixelar** tem intensidade mínima 8 (abaixo disso o texto pode ser reconstruído).
- **Executável.** O `Shotwise.exe` gerado pelo `build.bat` não é assinado, então o SmartScreen e alguns antivírus podem alertar (comum em executáveis do PyInstaller). Em ambiente corporativo, assine o executável ou execute via `run.bat`.
- **Dependências.** `requirements.txt` limita as versões maiores. Para builds reproduzíveis, gere um arquivo com hashes (`pip-compile --generate-hashes`) e instale com `pip install --require-hashes`.

## Ambiente corporativo (Device Guard / App Control)

Algumas empresas só deixam rodar programas assinados ou liberados por lista (WDAC, Device Guard, AppLocker). Nesse caso:

- `run.bat` costuma funcionar, porque roda pelo `python.exe` já liberado.
- Executáveis gerados com o PyInstaller (`Shotwise.exe`) e o instalador (`Shotwise-Setup-*.exe`) **não são assinados** e podem ser bloqueados. O erro típico é "foi bloqueado pela política do Device Guard".
- Saídas: (1) gerar o instalador em um computador sem essa política e distribuir por lá; (2) assinar com um certificado de código aceito pela empresa (veja **Assinatura de código** abaixo); (3) pedir ao suporte uma regra de liberação por hash ou por certificado para o `Shotwise.exe` e o instalador.
- **Instalador "modo Python" (`build_installer_python.bat`)**: não instala nenhum `.exe` novo. O Shotwise abre pelo `pythonw.exe` do Python já instalado (assinado pela Python Software Foundation, como no `run.bat`) e o instalador baixa PySide6 e numpy para a pasta do programa (precisa de Python 3.11+ e internet ou proxy). Gera `dist_installer\Shotwise-Python-Setup-<versão>.exe`. Usa o mesmo `AppId`, então atualiza instalações anteriores no mesmo lugar. O instalador em si ainda é um `.exe` sem assinatura; se a política bloquear até ele, use o `run.bat` ou peça liberação.
- O `build_installer.bat` mostra no final o SHA256 do `Shotwise.exe` e do instalador, para o pedido de liberação.
- Os scripts de build usam `python -m PyInstaller` (e não `pyinstaller.exe`), que a política costuma bloquear.

## Assinatura de código (opcional)

Os scripts de build assinam sozinhos quando há um certificado configurado; sem ele, geram tudo sem assinatura e avisam. Nada de senha vai para arquivo ou repositório: use variáveis de ambiente na janela do build.

```bat
set SHOTWISE_SIGN_PFX=C:\cofre\empresa-codesign.pfx
set SHOTWISE_SIGN_PASSWORD=sua-senha
rem opcional: carimbo de tempo da empresa (padrão: http://timestamp.digicert.com)
set SHOTWISE_SIGN_TIMESTAMP=http://tsa.suaempresa.local
build_installer.bat
```

- Atalho: `build_signed.bat` pergunta a senha e roda o `build_installer.bat` na mesma janela (usa `cert\shotwise-test.pfx`, ou o que estiver em `SHOTWISE_SIGN_PFX`). As variáveis `set` valem só na janela do CMD onde foram digitadas.
- Certificado já instalado no Windows (Meus certificados, token ou cartão): use `SHOTWISE_SIGN_THUMBPRINT` (impressão digital SHA1) no lugar de `SHOTWISE_SIGN_PFX` e `SHOTWISE_SIGN_PASSWORD` (`SHOTWIN_SIGN_THUMBPRINT` continua valendo).
- O `build_installer.bat` assina todos os `.exe`, `.dll` e `.pyd` de `dist\Shotwise` que ainda não têm assinatura válida (o App Control confere também as DLLs), depois o instalador e o desinstalador (`SignedUninstaller`). O `build_installer_python.bat` assina o instalador e o desinstalador; o `build.bat` assina o `Shotwise.exe` único.
- Precisa do `signtool.exe`. O `sign.bat` procura em `SHOTWISE_SIGNTOOL`, em `tools\signtool`, no PATH e no Windows SDK. Opções para obtê-lo: (1) Windows SDK, `winget install Microsoft.WindowsSDK.10.0.26100`, marcando só "Signing Tools for Desktop Apps"; (2) sem instalar nada: baixe o pacote NuGet `Microsoft.Windows.SDK.BuildTools` (https://www.nuget.org/api/v2/package/Microsoft.Windows.SDK.BuildTools), renomeie para `.zip`, extraia em `tools\signtool` e o `sign.bat` acha o `bin\<versão>\x64\signtool.exe`.
- Evite `"` e `%` na senha (`!` funciona). A senha aparece na linha de comando do `signtool` enquanto ele roda; prefira o build numa máquina de confiança.
- `tools\signing.ps1` ajuda: `-NewTestCert` cria um certificado de teste (autoassinado), `-Verify arquivo` confere a assinatura e `-Info arquivo` mostra assinante, emissor e cadeia (úteis para a regra do App Control).
- No App Control, a regra de "assinante" é criada uma vez pelo time que administra a política e vale para todas as versões assinadas pelo mesmo certificado. Guarde o `.pfx` em cofre: quem tem a chave assina o que o App Control aceita.

## Se o programa não abrir

- Rode `run_debug.bat`: abre com console, mostra o erro e grava o log detalhado.
- O log fica em `%APPDATA%\Shotwise\logs\shotwise.log` (e `crash.log` para falhas fatais). Também dá para abrir a pasta pelo menu da bandeja ("Abrir pasta de logs").
- O log registra eventos e erros, nunca imagens capturadas nem texto do OCR. Mesmo assim, revise antes de enviar a terceiros: os erros podem conter caminhos de pastas.

## Onde ficam os arquivos

- Capturas (PNG): `%USERPROFILE%\Documents\Shotwise` (altere nas configurações)
- Configurações: `%APPDATA%\Shotwise\config.json`
- Capturas editáveis: `%APPDATA%\Shotwise\library`
- Logs: `%APPDATA%\Shotwise\logs`

## Estrutura do projeto

```
main.py                    ponto de entrada
shotwise/app.py             bandeja, atalhos e fluxos de captura
shotwise/selector.py        seleção de área sobre a tela congelada (um overlay por monitor)
shotwise/scrollcap.py       rolagem automática + captura estável
shotwise/stitcher.py        costura dos quadros (numpy; independente de Qt)
shotwise/annotations.py     camadas de imagem, anotações, fundo, recorte, desfazer/refazer, exportação
shotwise/editor.py          janela do editor (barra de ícones, opções, salvar/reabrir)
shotwise/dialogs.py         diálogos de fundo, tamanho e biblioteca
shotwise/project.py         formato .shotwin (leitura validada)
shotwise/library.py         biblioteca local de capturas editáveis
shotwise/pin.py             janela de captura fixada
shotwise/preview.py         miniatura no canto após capturar
shotwise/ocr.py             reconhecimento de texto (Windows.Media.Ocr)
shotwise/logsetup.py        log em arquivo e captura de erros
installer/Shotwise.iss      script do instalador (Inno Setup)
build_installer.bat        gera app + instalador
build_installer_python.bat gera o instalador modo Python (sem .exe do programa)
installer/Shotwise-Python.iss  script do instalador modo Python
shotwise/hotkeys.py         atalhos globais (RegisterHotKey via ctypes)
shotwise/settings_dialog.py janela de configurações
tests/                     testes (costura e editor)
```

## Testes

```
pip install pytest
python -m pytest tests -q
```

Os testes de costura, do editor, do formato de projeto e da seleção rodam sem tela (modo offscreen). A captura da tela real, os atalhos globais, a rolagem automática, o instalador e a exclusão do histórico da área de transferência dependem do Windows e precisam ser verificados manualmente.

## Próximos passos possíveis

- Captura de janela ativa
- Cronômetro (captura com atraso)
- Detecção automática de dados sensíveis por OCR para sugerir tarjas
- Gravação de tela

- **Linha e seta:** o ponto azul no meio do traço curva a linha; o controle "Curvatura" faz o mesmo. **Preenchimento** de retângulo e elipse tem controle de opacidade. **Tema:** Escuro, Claro ou Seguir o sistema (Configurações).
- **Fundo:** na ferramenta Fundo, escolha o estilo (cores saindo do centro, misturadas pelas extremidades ou desfoque suave), um degradê pronto ou uma cor, e ligue/desligue a sombra. Margem e cantos continuam nas alças da imagem.
- **Lupa:** seta curva ligando a região à ampliação (arraste o ponto azul para curvar; a opção "Seta" liga e desliga).
- **Abrir com:** o instalador registra o Shotwise em "Abrir com" e em "Editar no Shotwise" para PNG, JPG, BMP e WebP. Se o Shotwise já está aberto, a imagem abre nele.
- **Biblioteca:** limite por quantidade de arquivos e por tamanho (MB); as capturas mais antigas saem primeiro.
- **Idioma:** Português, English e Español em Configurações (vale ao reabrir o Shotwise).
- **Refazer:** `Ctrl+R`.

**Zoom e rotação**: no rodapé há −/+/⤢, uma barra deslizante de zoom e o botão **100%** (tamanho original). Na ferramenta Redimensionar, ⟲/⟳ giram a imagem (as anotações são incorporadas).

**Configurações em abas** (Geral, Captura, Vídeo e GIF, Sobre). Em *Geral* há a opção **Ocultar notificações** (avisos de erro continuam). Em *Captura* ficam o **Nome dos arquivos** (códigos de data como `%Y-%m-%d_%H-%M-%S`, com exemplo ao vivo; se o nome já existir, acrescenta `_2`, `_3`…) e **Salvar em subpastas por ano e mês** (`pasta de capturas\2026\11`). Vale para imagens, GIF e vídeo.

**Atualização** (origem e opção de verificar ao iniciar na aba *Geral*; botão *Verificar atualizações* na aba *Sobre*): escolha a origem.
- *Repositório (internet)*: o Shotwise lê a última *Release* do repositório padrão (definido em `UPDATE_REPO_DEFAULT`, em `shotwise/__init__.py`) e baixa o instalador (somente HTTPS, inclusive nos redirecionamentos).
- *Pasta local ou de rede*: coloque na pasta o instalador `Shotwise-Setup-X.Y.Z.exe` (ou `Shotwise-Python-Setup-X.Y.Z.exe` para o modo Python) e o arquivo `<instalador>.sha256` (ou um `latest.json` com `{"version": "X.Y.Z", "file": "Shotwise-Setup-X.Y.Z.exe", "sha256": "..."}`). Os scripts `build_installer.bat` e `build_installer_python.bat` já geram o `.sha256` depois de assinar. Conceda gravação nessa pasta só a administradores.

**Publicar uma versão para atualização pela internet (GitHub Releases)**
1. Em `shotwise/__init__.py`, aumente `__version__` e informe `UPDATE_REPO_DEFAULT = "usuario/repositorio"` (e, se quiser, `UPDATE_SIGNER_DEFAULT` com a impressão digital do certificado).
2. Rode `build_signed.bat` (gera `Shotwise-Setup-X.Y.Z.exe` assinado e o `.sha256` em `dist_installer`).
3. Envie o código ao repositório (`git add`, `git commit`, `git push`). Não envie `.pfx`, senhas nem `dist_installer` (o `.gitignore` já cobre).
4. Rode `publicar_release.bat` (usa o GitHub CLI) ou crie a Release pelo site com a tag `vX.Y.Z` e anexe o instalador **e** o `.sha256`. O Shotwise usa a Release marcada como mais recente e confere o hash e a assinatura antes de instalar.
5. O repositório precisa ser **público** para a consulta sem login funcionar (repositório privado devolve erro 404). Para repositório privado use a origem por pasta/rede.

**Verificações antes de instalar**: (1) o SHA-256 é obrigatório: sem ele a atualização é recusada; (2) o instalador precisa ter assinatura digital válida (Authenticode); (3) se `update_signer` (em `%APPDATA%\Shotwise\config.json`, ou `UPDATE_SIGNER_DEFAULT` no código) tiver uma ou mais impressões digitais (SHA-1, separadas por vírgula), só instaladores assinados por esses certificados são aceitos. Para pegar a impressão digital: `Get-AuthenticodeSignature .\Shotwise-Setup-X.Y.Z.exe | Select -Expand SignerCertificate | Select Thumbprint`. Em ambiente de teste sem assinatura, defina `"update_require_signature": false` no `config.json` (não recomendado em produção). O download tem limite de 600 MB e o manifesto, de 1 MB.

O botão *Verificar atualizações* consulta a origem; *Baixar e instalar* pede confirmação, executa o instalador em modo silencioso e fecha o programa. A opção *Verificar atualizações ao iniciar* avisa pela bandeja.

**Atualizações no instalador**: o instalador tem uma página *Atualizações* (repositório web, que é o padrão, ou uma pasta local/de rede). A escolha é gravada em `%APPDATA%\Shotwise\install_defaults.json` e aplicada na primeira abertura do Shotwise. Para instalar em vários computadores sem tela, passe a pasta por parâmetro:

```
Shotwise-Setup-X.Y.Z.exe /VERYSILENT /SUPPRESSMSGBOXES /UPDATEFOLDER="\\servidor\compartilhamento\Shotwise"
```

Sem `/UPDATEFOLDER`, uma instalação silenciosa (inclusive a feita pelo próprio atualizador) não mexe na origem de atualização já configurada. O repositório web padrão e o nome exibido em *Sobre* ficam em `shotwise/__init__.py` (`UPDATE_REPO_DEFAULT` e `APP_AUTHOR`).

**Vídeo MP4**: `Alt+Shift+V` (ou o menu da bandeja) grava a área escolhida, com a mesma barra, a mesma janela de revisão e os mesmos recursos do GIF (segmentos, dividir, excluir, girar, zoom, destaque e recorte). Para tirar trechos do meio, divida nas duas pontas e exclua o segmento do meio; repita quantas vezes quiser (cada passo tem Desfazer), e o que sobrar é emendado no vídeo final. **Abrir vídeo ou GIF já salvo**: o Shotwise aparece em "Abrir com" e no menu "Editar no Shotwise" dos arquivos `.mp4` e `.gif` (o instalador registra isso), e também abre por *Abrir*. O arquivo é lido no player para dividir, excluir, girar, zoom etc. e salvo como um arquivo novo (o original não é alterado). O MP4 volta com o áudio; para caber na memória o vídeo é reduzido à largura máxima e aos quadros por segundo das configurações de vídeo. Leitura de até 15 minutos.

O arquivo vai para a pasta de capturas, com o nome definido em *Configurações > Captura > Nome dos arquivos*, e também é copiado para colar em e-mail ou chat. Não precisa de ffmpeg nem de outro programa: usa o codificador do Qt Multimedia, com H.264 quando o Windows oferece e MPEG-4 como alternativa automática. **Áudio**: o vídeo grava o som do sistema (o que toca nas caixas de som) e o microfone, misturados numa faixa AAC. O som do sistema usa o componente opcional PyAudioWPatch (`requirements-audio.txt`, só Windows); sem ele o app avisa e grava só o microfone. Dividir, excluir e cortar trechos acompanham o áudio. O GIF não tem som, e a revisão antes de salvar toca sem som. Em *Configurações > Vídeo e GIF* ficam as caixas de som do sistema e microfone (com escolha do dispositivo), a fluidez, a duração, a largura e a memória máxima (os quadros ficam na memória até salvar; largura menor e menos quadros por segundo rendem gravações mais longas).
