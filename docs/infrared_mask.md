# Zephyr · máscara infravermelha SPHEREx / MPC

O laboratório também oferece [mosaico IR em falsas cores](infrared_color.md),
exclusivamente para estética, com cobertura por canal e exportação PNG.

Este laboratório seleciona pixels em toda a cobertura nominal SPHEREx, **0,75–5,00 µm, detectores D1–D6**. O padrão usa 12 exposições; o limite configurável é 72, com até 144 candidatos inspecionados. A seleção distribui oportunidades entre detectores e épocas, em vez de preencher o limite com uma única banda. O processamento é local, em Python/Astropy; Zephyr exibe os resultados, sem recalcular fotometria no navegador.

| Detector | Intervalo nominal (µm) |
| --- | --- |
| D1 | 0,75–1,09 |
| D2 | 1,10–1,62 |
| D3 | 1,63–2,41 |
| D4 | 2,42–3,82 |
| D5 | 3,83–4,41 |
| D6 | 4,42–5,00 |

Esses limites descrevem os detectores segundo a [documentação dos produtos SPHEREx](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/). Os valores científicos vêm dos mapas CWAVE/CBAND oficiais de cada detector; podem diferir ligeiramente dos limites nominais. A cobertura observada é discreta: poucos FITS não fornecem todos os canais nem um espectro contínuo. Bandas sem exposição ou sem abertura aceita aparecem explicitamente sem medida.

O gráfico usa o comprimento de onda médio CWAVE da abertura no eixo X, fluxo em µJy e barras verticais ±1σ; a barra horizontal indica CBAND. Não há interpolação. Exposições em épocas e bandas diferentes não são um espectro simultâneo nem uma curva de luz em banda fixa. O seletor de detector filtra o player e a tabela; a escala de imagem é compartilhada apenas dentro do mesmo detector.

**Escopo científico:** a cobertura ampliada é a dos FITS SPHEREx disponíveis. Gaia fornece astrometria e contaminação estelar. WISE permanece uma referência contextual; não há nesta análise exposições WISE de objetos móveis com fotometria compatibilizada. Seus filtros não são inventados nem anexados ao espectro SPHEREx como se fossem medidas equivalentes.

## Rodar no Windows

Na raiz deste repositório:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-infrared.txt
.venv\Scripts\python.exe scripts/infrared_lab.py calibration --detector all
.venv\Scripts\python.exe scripts/infrared_lab.py archive --calibration data/infrared/calibrations --coordinates sky
.\start-infrared.ps1
```

Abra **http://127.0.0.1:8766/**: a página inicial é a versão integrada de `zephyr_spherex_planet_x_interactive.html`, em `web/site/index.html`, com o modelo 3D e a identidade Zephyr preservados. **http://127.0.0.1:8766/lab** abre o laboratório com a mesma logo, tipografia, fundo escuro, bordas e acentos vermelhos. O servidor só escuta na máquina local. O comando `archive` usa o asteroide **1766 / Slipher** e 20–25/07/2026 como caso inicial, sem afirmar detecção. Outros objetos/datas, detectores e janelas podem ser consultados no painel. O intervalo máximo é sete dias. Não encontrar cobertura gera uma mensagem explícita.

O download inicial de calibração tem cerca de 33 MB **por detector** (aproximadamente 200 MB para os seis). `calibration` consulta o índice público oficial e registra a versão exata e SHA-256; se houver múltiplas versões, exige seleção explícita. Os arquivos ficam em `data/infrared/calibrations/calibration_D1.fits` até `calibration_D6.fits`. Um arquivo de calibração único só habilita o detector correspondente; detectores incompatíveis são rejeitados. O arquivo de imagem original permanece intacto. O certificado TLS sempre é verificado; no Windows, `truststore` usa as autoridades do sistema.

Para uma janela estreita, por exemplo:

```powershell
.venv\Scripts\python.exe scripts/infrared_lab.py archive --detector 4 --low-um 3.35 --high-um 3.45 --max-exposures 4
```

Os assets da página inicial já estão compilados e o servidor Python os entrega localmente, incluindo Three.js. Para recompilar o CSS da home: `npm.cmd ci --prefix web/site`, `npm.cmd run build --prefix web/site` e `npm.cmd run check --prefix web/site`. Fontes Google são opcionais e têm fontes locais de fallback.

Para verificar o fluxo sem rede, gere **dados explicitamente sintéticos**, separados da análise real:

```powershell
.venv\Scripts\python.exe scripts/infrared_lab.py demo
.venv\Scripts\python.exe scripts/infrared_lab.py serve --output outputs/infrared_demo
```

O painel mostra um aviso permanente quando os dados são sintéticos. Nenhum erro de rede aciona essa demonstração automaticamente.

## Dados e coordenadas

- **MPC**: identificação e elementos orbitais. Não é a fonte das imagens FITS. `archive --mpc-orbit-file orbit.txt` aceita uma linha de elementos de um asteroide no formato MPC, encaminhada ao MOST com `input_type=mpc_input`. Sem esse argumento, a identificação é resolvida pelo MOST; a proveniência não a apresenta como um download direto de órbita MPC.
- **SPHEREx / IRSA**: recortes das exposições, WCS celeste principal (ICRS/TAN-SIP), IMAGE, VARIANCE, FLAGS, ZODI e calibração CWAVE/CBAND.
- **Gaia DR3 / ESA**: catálogo de contaminação estelar, G < 19 por padrão; os movimentos próprios disponíveis são propagados da época do catálogo para cada exposição. Não é um mapa de fluxo infravermelho. Falhas e truncamento da consulta ficam registrados.
- **WISE**: não é subtraído do SPHEREx. W1 é uma banda larga, diferente da janela estreita; uma comparação fotométrica futura exige convolução das respostas e controle de época/PSF/unidades.

O MOST retorna coordenadas e exposições associadas ao identificador orbital. **O observador dessas posições ainda precisa ser validado para astrometria de precisão**: a saída é marcada `observer_not_verified`. Não se aplica uma correção de paralaxe inventada. Efemérides ICRS calculadas para o observador correto podem entrar por manifesto local. A época de cada posição deve estar a no máximo 60 s do `MJD-AVG` da exposição; `DATE` é criação de arquivo e nunca define a época científica. Uma medida na posição prevista não comprova presença ou associação do objeto.

## Algoritmo e limites

1. Valida detector D1–D6, compatibilidade da janela/detector, unidades de brilho superficial, formas dos HDUs e WCS. Aceita recortes de até 256 × 256 pixels. Exposições simultâneas de detectores distintos permanecem independentes: a chave de aquisição inclui observação **e** detector.
2. Alinha os mapas completos CWAVE/CBAND ao recorte usando o WCS alternativo **A, origem zero**. Na forma linear comum, `x_detector = 1 + x_cutout - CRPIX1A`. A orientação `DETCOORD` é respeitada: só se inverte X em D4–6 quando imagem e calibração usam orientações diferentes. Mapas externos sem orientação exigem declaração explícita.
3. Seleciona `low_um <= CWAVE < high_um`, com CBAND finito e positivo. O WCS-WAVE aproximado só filtra downloads candidatos; nunca fornece a calibração científica. O CBAND medido é exportado: selecionar centros de banda não estreita a resposta física do instrumento nem reconstrói um cubo monocromático.
4. Rejeita flags instrumentais `0x0A02CEC7`, preservando SOURCE/FULLSAMPLE e registrando OUTLIER e demais flags de revisão. A política deriva do contrato SkyShift e foi conferida contra `MSKNnnnn` de um FITS D4 real. Flags desconhecidas são contabilizadas. Isso permite revisar fontes móveis, mas artefatos de revisão ainda podem contaminar uma medida.
5. Sinaliza regiões a 12,4″ de fontes Gaia selecionadas. Sem movimentos próprios, mantém a posição catalogada e registra a limitação. Essa máscara não substitui um catálogo completo de fontes IR nem uma modelagem de PSF.
6. Subtrai ZODI apenas quando o HDU está presente e essa opção está habilitada. O fundo local vem da mediana do anel de 4–7 pixels. Abertura de 2 pixels, com pesos de subpixels 5 × 5. Qualquer perda significativa de cobertura na abertura, borda ou fundo insuficiente impede a medida; não se extrapola fluxo ausente.
7. Converte brilho superficial em µJy usando a área sólida local derivada do WCS. Erro: variância por pixel com pesos ao quadrado, mais incerteza da mediana do fundo. A variância do fundo usa o maior valor entre dispersão robusta e variância instrumental. Se VARIANCE não informa unidade, assume o quadrado da unidade IMAGE, conforme o produto da missão.

Os fluxos são **de abertura, sem correção de PSF**. Não incluem erros sistemáticos da calibração, modelo zodiacal, posição prevista, incerteza da máscara ou covariância entre pixels. S/N é condicional a essas hipóteses, não significância global de descoberta. O movimento durante a exposição não é corrigido. Não há detecção automática, órbita ajustada, classificação de Planet X ou limite superior calculado para aberturas rejeitadas.

Cada imagem é mostrada em sua grade nativa, com o seu WCS e uma escala de brilho comum **por detector**. A trajetória prevista é projetada novamente para o WCS de cada exposição; alternar frames não é um mosaico registrado e estrelas podem mudar de pixel. A fotometria usa sempre os pixels originais, sem reamostragem. A figura PNG limita a prévia a 12 imagens, distribuídas entre os detectores; todas as exposições aceitas permanecem no player, CSV, JSON e FITS.

## Entradas locais reproduzíveis

```json
{
  "object": "Identificação MPC",
  "synthetic": false,
  "config": {"low_um": 3.35, "high_um": 3.45, "max_exposures": 2},
  "gaia_status": "not_supplied",
  "gaia": [],
  "exposures": [
    {
      "fits": "exposicao_1.fits",
      "calibration": "calibration_D4.fits",
      "calibration_coordinates": "sky",
      "target": {"ra": 28.0, "dec": 11.0, "mjd": 61241.24668,
                 "frame": "ICRS", "provider": "Efeméride fornecida",
                 "position_status": "observer_not_verified"}
    }
  ]
}
```

Os números do exemplo são apenas estrutura, não um conjunto observado para executar. Preencha com a posição correspondente ao FITS. Caminhos relativos são resolvidos junto ao manifesto. Também são aceitos CWAVE/CBAND já alinhados como HDUs embutidos (`DETCOORD=cutout`), com BUNIT explícito. Não se pode usar a pasta dos originais como saída.

```powershell
.venv\Scripts\python.exe scripts/infrared_lab.py run caminho/manifest.json --output outputs/minha_analise
.venv\Scripts\python.exe scripts/infrared_lab.py serve --output outputs/minha_analise
```

## Saídas

- `exposure_XX.fits`: IMAGE, SCIENCE, MASKED, VARIANCE, CWAVE, CBAND, MASK e FLAGS, WCS, limites da janela, política de flags e checksum FITS. Pixels rejeitados ficam NaN em MASKED.
- `measurements.csv`: detector, CWAVE na posição prevista, UTC, coordenadas e origem da posição, estado, fluxo/erro em µJy, S/N, cobertura, λ médio e largura efetiva média na abertura.
- `report.json` (schema 3): arrays para visualização, `spectral_coverage` com contagens e centros efetivamente amostrados por detector, contagens de máscara, SHA-256 das entradas/saídas/calibrações, configurações, proveniência e limitações. NaN é serializado como `null`.
- `manifest.json`: reprodução das entradas. Tabelas MOST/Gaia e metadados dos downloads ficam no cache em `data/infrared/`.

Bits de MASK: INVALID=1, INSTRUMENT=2, OUTSIDE_BAND=4, GAIA=8, NO_CALIBRATION=16, ADVISORY=32, TARGET_APERTURE=64. Apenas `1|2|4|8|16` rejeitam um pixel. TARGET_APERTURE marca a região de medida, não um objeto detectado.

## Contexto dos repositórios e referências

Foram consultados `skyshift/CLAUDE.md`, `.claude/settings.json`, `contracts/flags.md`, os documentos de pesquisa de primeira exposição/link-check e as referências científicas apontadas ali; GhostShift orientou a separação por exposição e revisão de alvos móveis, Blackhole-SPHEREx a distinção entre espectro, PSF e imagem, e este repositório forneceu a base FITS/WCS e o Sky Explorer. O novo módulo preserva os comandos e políticas dos experimentos anteriores; não altera globalmente `quality.py`. As regras de implantação do SkyShift não se aplicam a este servidor local em outro repositório.

Fontes primárias verificadas:

- [SPHEREx: produtos, CWAVE/CBAND e recortes](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
- [SPHEREx: acesso aos arquivos](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/)
- [Calibrações espectrais IRSA](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/spherex_spectral_calibrations.html)
- [MOST: interface e entrada MPC](https://irsa.ipac.caltech.edu/applications/MOST/MOSTProgramInterface.html)
- [Gaia DR3 no IRSA](https://www.ipac.caltech.edu/doi/10.26131/IRSA544)
- [MPCORB](https://www.minorplanetcenter.net/iau/MPCORB.html)

Testes: `PYTHONPATH=src python -m pytest tests/test_infrared_mask.py` (no PowerShell: `$env:PYTHONPATH='src'` antes do comando). Cobrem fluxo/unidades/incerteza com sinal conhecido, flags SOURCE/OUTLIER, contaminação Gaia, WCS de origem zero e inversão MWIR, época de observação, limites de entrada, preservação dos originais, checksum e rotas HTTP locais.

## Validação real D1–D6

O conjunto padrão foi reprocessado em 15/11/2026 com 12 exposições reais QR3 de Slipher no intervalo 20–25/07/2026. Houve 3, 2, 1, 3, 2 e 1 exposições em D1, D2, D3, D4, D5 e D6, respectivamente, todas com abertura aceita. Os centros CWAVE na posição prevista vão de aproximadamente 0,8072 a 4,9957 µm; isso amostra os seis detectores, sem preencher os intervalos não observados. A calibração é `cal-swcs-v5-2026-191` por detector; o catálogo Gaia carregado reuniu 261 fontes antes do filtro por imagem. As posições continuam `observer_not_verified`: o resultado valida a execução e a cobertura, não uma detecção.

O exemplo D5 de 3,8008 µm ilustra por que os intervalos nominais da tabela não substituem CWAVE. Cada mapa oficial é usado diretamente, sem ajustar o comprimento de onda para caber no rótulo do detector.

```powershell
.venv\Scripts\python.exe scripts/infrared_lab.py archive --max-exposures 12
```

## Histórico: validação inicial restrita a D4

Em 15/11/2026, foram processadas três exposições QR3 de **1766 / Slipher**, observadas em 22/07/2026: `2026W30_1B_0509_1`, `_2` e `_3`, detector D4. A seleção explícita foi **3,30–3,50 µm**. Os centros médios nas aberturas foram aproximadamente 3,30494, 3,39541 e 3,48826 µm, respectivamente; CBAND cerca de 0,094–0,097 µm. Essas exposições não têm exatamente o mesmo centro de banda: mudanças de fluxo entre elas não são, isoladamente, variabilidade temporal.

A janela inicial mais estreita **3,35–3,45 µm** retornou apenas uma exposição para esse objeto/período. O programa preserva essa diferença de cobertura. Para reproduzir as três imagens:

```powershell
.venv\Scripts\python.exe scripts/infrared_lab.py archive --low-um 3.30 --high-um 3.50 --calibration data/infrared/calibration_D4.fits --coordinates sky
```

Calibração oficial usada: `qr3/spectral_wcs/cal-swcs-v5-2026-191/4/spectral_wcs_D4_spx_cal-swcs-v5-2026-191.fits`, mapas 2040 × 2040, DETCOORD=sky. O índice do arquivo foi consultado porque os exemplos da documentação usam outro nome de versão. Gaia DR3 foi obtido pela interface Gator do IRSA (41 fontes com G < 19); TAP retornou erro temporário. O relatório e os arquivos `.source.json` registram URLs e SHA-256. Estes dados estão no cache local ignorado pelo Git; o código permite baixá-los novamente.

As três aberturas passaram nos critérios de cobertura e máscara. Isso valida a execução do processamento, **não a associação astrométrica ou a detecção do asteroide**. As posições MOST continuam marcadas `observer_not_verified`. Os testes HTTP e de comportamento JavaScript passam. A figura científica PNG é gerada e pode ser inspecionada independentemente do navegador.

## Display com o escopo SkyShift

O relatório acrescenta `plot` por exposição e `plotting` para a seleção das imagens, mantidos na versão 3. A implementação adapta a política de `learn/data.ts`, `learn/plate.ts` e `blink/math.ts` do SkyShift; veja [atribuição e licença](../third_party/skyshift/README.md).

- **Recorte MPC/MOST:** quadrado de no mínimo 40 pixels, com margem de 12 pixels em torno das previsões cobertas da mesma sessão (até 10 minutos da exposição). Os limites permanecem dentro do FITS. Pontos externos não aumentam o recorte. Há uma opção para ver o campo FITS completo.
- **Compatibilidade:** uma previsão só entra na plotagem quando seu pixel tem imagem finita, variância válida, calibração disponível, qualidade instrumental aceitável e centro de banda dentro da janela escolhida. Exposições sem essa cobertura permanecem no relatório/FITS/CSV para auditoria, mas são excluídas do player.
- **Gaia:** as posições propagadas são filtradas por WCS, limites do recorte e pixel efetivamente disponível. Na vista de faixa aplicada, também se exige compatibilidade espectral. Os círculos representam posições de catálogo, não detecções independentes. Um catálogo explicitamente indisponível não fornece círculos nem uma máscara estelar a partir de registros antigos.
- **Trajetórias:** segmentos não atravessam pontos externos, pixels sem cobertura ou épocas de outras sessões. O canvas recorta os desenhos nos limites da imagem; não há marcadores na margem.
- **Brilho:** a mediana local é removida apenas para display; o asinh usa os mesmos limites robustos entre exposições do mesmo detector. Original e SCIENCE têm fundos próprios; SCIENCE e sua versão mascarada compartilham exatamente a escala. O controle de contraste não altera a fotometria. Pixels sem dado aceito ficam hachurados no painel e cinza na figura PNG.
- **Geometria:** pixels nativos, proporção preservada, eixos X/Y com os índices originais, orientação N/E calculada pelo WCS e tamanho angular aproximado do campo. Não se presume que o eixo Y do detector seja norte.

Para as três exposições Slipher já usadas: as 41 fontes Gaia vieram de uma consulta maior que o recorte. Há 22, 22 e 21 posições em pixels com cobertura/qualidade válida no campo completo; no recorte MPC de 40 × 40 restam **8, 8 e 7** posições, antes do filtro específico da vista espectral. A exclusão de fontes fora da imagem não constitui, por si só, evidência de falha do Gaia. Neste conjunto, o catálogo foi carregado pelo Gator e sua proveniência é preservada.

Na validação inicial D4, os fluxos e incertezas permaneceram iguais aos da análise anterior após a mudança de display. Os FITS de saída mantêm 70 × 70 pixels: o recorte de display não altera as entradas nem reamostra a fotometria. `comparison.png`, disponível no botão **Plotagem PNG**, reúne contexto e faixa aplicada para até 12 exposições, com escala comum por detector.

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/test_infrared_bands.py tests/test_infrared_mask.py tests/test_infrared_display.py -q
node --test web/infrared-mask/app.test.mjs web/infrared-mask/plate.test.mjs
```
