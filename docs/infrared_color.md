# Mosaico infravermelho em falsas cores

A implementação usa o conceito de cubo `(x, y, λ)` do
[tutorial SPHEREx/IRSA](https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/)
para **colorir imagens**, com uma compressão estética em três janelas IR.
O tutorial fornece a referência para a estrutura do cubo e a associação entre planos
e comprimentos de onda; a escolha destas cores e janelas é uma adaptação Zephyr.
Não é necessário extrair espectros, subtrair contínuo PAH ou buscar imagens UV/ópticas.

| Cor de exibição | Centros de banda aceitos |
| --- | --- |
| Vermelho (R) | 3,83 ≤ λ ≤ 5,00 µm |
| Verde (G) | 1,63 ≤ λ < 3,83 µm |
| Azul (B) | 0,75 ≤ λ < 1,63 µm |

Essas janelas são fixas e não mudam quando faltam observações. São agrupamentos para
display, não novos filtros físicos. Uma composição com apenas verde disponível é
mostrada como verde; não são inventados outros canais. A cobertura de cada canal e
a fração com RGB completo aparecem no painel e nos metadados. A janela de seleção
do laboratório continua sendo aplicada antes da composição.

## Exposições nativas do laboratório

`run`, `archive`, `demo` e os novos processamentos pelo painel geram automaticamente
`color_mosaic.png`, `color_mosaic_rgba.png` e `color_mosaic.json`, além dos produtos
anteriores. `report.json` recebe a propriedade opcional `color_mosaic`.
Relatórios anteriores continuam utilizáveis; reprocessá-los gera a nova composição.

1. Usa somente exposições elegíveis segundo a cobertura MPC/MOST já existente.
2. Mantém a grade celeste e o campo da primeira exposição elegível em ordem temporal.
   Os outros campos são mapeados para ela por seus WCS, com amostragem do pixel
   nativo mais próximo. Dados fora desse campo não entram nesta prévia.
3. Seleciona a cor pelo CWAVE oficial de cada pixel de origem, e não pelo número do
   detector. Respeita os bits INVALID, INSTRUMENT, OUTSIDE_BAND e NO_CALIBRATION.
   Gaia permanece visível como contexto estelar; a máscara científica Gaia permanece
   aplicada à fotometria e à vista “Faixa aplicada”.
4. Combina contribuições válidas com média simples por canal, sem interpolar lacunas.
   Cada pixel fornece seu brilho superficial, em MJy/sr, sem conversão a fluxo por
   pixel da nova grade. Trata-se exclusivamente de uma reamostragem para display.
5. Subtrai a mediana de cada plano combinado somente para exibição e aplica percentis
   robustos e `asinh(10)`, seguindo a política visual SkyShift. Cada canal tem seu
   próprio contraste; as cores não fornecem razões de fluxo calibradas.

FITS, fotometria, variâncias, flags, posições e comparações temporais continuam no
[pipeline nativo baseado no SkyShift](infrared_mask.md). O módulo de cor não escreve
nos arquivos científicos nem altera os arrays de entrada. Não há tratamento óptico,
UV ou extrapolação para comprimentos de onda fora de 0,75–5,00 µm.

É uma composição de épocas distintas: objetos móveis podem aparecer em várias
posições. Sem ajuste de PSF, as cores também dependem de resolução, ruído e cobertura.
Não há alinhamento artificial na posição do objeto. O player nativo continua
disponível para inspecionar cada exposição e sua época separadamente.

## Colorir um cubo FITS do IRSA

Na raiz do novo clone, após instalar `requirements-infrared.txt`:

```powershell
.venv\Scripts\python.exe scripts/infrared_lab.py colorize-cube caminho\cubo_irsa.fits --output outputs\minhas_cores
```

O cubo deve ter `IMAGE` tridimensional com unidade de brilho superficial conversível
para MJy/sr, `NHITS` e `FLAGS` alinhados, WCS celeste e a tabela `WCS-WAVE`.
Os índices `PLANE` são verificados e reordenados; `WAVELENGTHS` fornece os comprimentos
de onda e sua unidade FITS é respeitada (µm quando não declarada).
Planos fora do infravermelho SPHEREx são ignorados. Pixels com NHITS zero ou flags
rejeitadas pela política SkyShift não contribuem; SOURCE e OUTLIER são preservados.
A composição usa a grade já registrada do IRSA e a média dos planos cobertos em
cada janela RGB. Não reexecuta a análise fotométrica do tutorial.

O original é aberto somente para leitura. A pasta de saída deve ser separada da pasta
do cubo. A saída contém a figura com eixos celestes, um raster RGBA transparente onde
nenhum canal tem cobertura e metadados com SHA-256, canais, limites e cobertura.

## Validação

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/test_infrared_color.py tests/test_infrared_display.py tests/test_infrared_mask.py tests/test_infrared_bands.py -q
node --test web/infrared-mask/app.test.mjs web/infrared-mask/plate.test.mjs
```

Os testes verificam alinhamento de WCS distintos, fronteiras espectrais, lacunas,
SOURCE/Gaia, unidades da tabela IRSA e preservação dos arquivos e medidas científicos.

Validação local em 15/11/2026: as 12 exposições reais de Slipher foram reprocessadas,
com todas as medidas de abertura e arrays dos HDUs científicos idênticos ao relatório
anterior. Na grade da primeira exposição, apenas três exposições contribuem: a
cobertura é aproximadamente R=0%, G=99,90%, B=69,33%; não há pixels com RGB completo.
Isso é mostrado explicitamente, sem preencher vermelho a partir de outro campo.
O cubo real M101 do tutorial também foi colorido, com cobertura RGB completa em
aproximadamente 99,99% dos pixels. Os dados locais permanecem ignorados pelo Git.
