# Aplicação web SPHEREx

**Site público: [SPHEREx Sky Explorer](https://spherex-sky-explorer-2026.melodicember8.chatgpt.site)**

A aplicação está em **[web/sky-explorer](web/sky-explorer)**. Ela oferece busca por coordenadas,
animação temporal com banda fixa, seis detectores/102 canais, campo ajustável, média/diferença,
GIF, espectro em abertura e sobreposições Aladin/Gaia/WISE. Há cinco exemplos reais prontos: 
Barnard, Epsilon Indi B, WISE 0855, RW Aur e R Dra.

```bash
cd web/sky-explorer
npm ci
npm run build
npm run dev
```

Acesse http://localhost:4173. Consulte o README da aplicação para métodos, testes e limites.

# SPHEREx: três mosaicos processados e um GIF

O resultado principal é o **[GIF das três visitas processadas](outputs/three_visits/spherex_three_visits.gif)**.
O programa processa os três mosaicos originais de maio/2025, novembro/2025 e
abril/2026 (respectivamente 3, 7 e 5 exposições combinadas) e depois monta um GIF
com esses três resultados, em ordem de data.

```bash
uv sync --extra viz --extra dev --extra ml
uv run --extra viz spherex-tracking three-visits
```

Abra `notebooks/11_visualizacao_ipyaladin.ipynb` ou `notebooks/12_cubo_102_bandas.ipynb`.
Ambos mostram o GIF, as três imagens lado a lado, a fotometria e o seletor de
visita no Aladin. O pipeline aplica WCS celeste, reprojeção, conversão de MJy/sr
para mJy/pixel e fotometria/subtração de fundo em anel, seguindo essas etapas do
[tutorial IRSA](https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/).
A escala visual é fixa para todas as imagens. Os três FITS processados e o
relatório estão em `outputs/three_visits/`.

Os mosaicos de entrada são imagens 2D da mesma seleção espectral ampla D6
(4,885 ± 0,120 µm). Eles não contêm os planos espectrais necessários para a
subtração de contínuo PAH de 3,3 µm do exemplo M101. O código não transforma
um único cubo espectral em três épocas. Os produtos anteriores em
`outputs/temporal_band/` e `outputs/spectral_cube/` são experimentos auxiliares;
o GIF principal agora usa as três visitas completas.

A branch também inclui os dados FITS, catálogos, modelos e demais resultados
locais. Abaixo está o histórico dos outros experimentos.

# Objetos móveis fracos: Shift-and-Stack

Protótipo executável em Python inspirado em Wang, Zhao e Li (2018),
**Detection of Faint Asteroids Based on Image Shifting and Stacking Method**,
[DOI: 10.1016/j.chinastron.2018.09.007](https://doi.org/10.1016/j.chinastron.2018.09.007).

O primeiro experimento injeta um objeto com SNR individual esperado próximo de 2,2
em 32 exposições com estrelas, fundo variável e ruído. A busca recebe as imagens e
uma grade de velocidades, sem acesso à trajetória verdadeira. As posições
injetadas entram apenas nas métricas de validação. Os dados são **simulados**;
o resultado ainda não demonstra viabilidade no SPHEREx.

## Mais dados reais: oito regiões SPHEREx + Gaia

```bash
uv run --extra ml spherex-tracking expand
```

O padrão seleciona oito exposições por região em oito regiões do céu, usando
Astroquery/IRSA para SPHEREx e consultas Gaia assíncronas sem o corte de 2.000
linhas. Os recortes têm 0,6 grau por lado. Arquivos e consultas são preservados
em `data/expanded/`; exemplos, partições e modelo ficam em `outputs/expanded/`.
Abra `notebooks/09_treino_ampliado_spherex.ipynb`.

O teste reserva regiões inteiras: cinco para treino, uma para validação e duas
para avaliação final. Identidades Gaia e coordenadas instrumentais repetidas
nas partições anteriores são retiradas das posteriores. Não há injeções.
O limite do treinamento continua em 120 segundos, incluindo o processo filho.
`--per-field` aumenta ou reduz o número de exposições solicitadas por região.

Após um treinamento concluído, `outputs/active_observed_model.json` aponta para
o modelo ampliado. O comando `sprints` passa a usá-lo. O ranking da demonstração
fica em `outputs/expanded_demo/`; seus oito quadros originais não devem ser
confundidos com todo o conjunto de treino e teste, que cobre novos campos.
A classificação permanece fonte observada/contaminação instrumental em imagens
nativas. A avaliação independente é desse problema, não de descoberta de asteroides.

## Animação temporal SPHEREx estilo WiseView

```bash
uv run --extra viz spherex-tracking timelapse
```

Consulta o ponto do céu do link WiseView (RA 133.786245°, Dec −7.244372°),
baixa as imagens públicas SPHEREx D6 e monta um GIF alinhado no mesmo campo de
176 segundos de arco. No URL do WiseView, `size=176` é o campo em segundos de
arco, não 176 pixels. Como os pixels SPHEREx são maiores que os pixels WISE, o
recorte contém cerca de 28 amostras nativas por lado.

O arquivo `outputs/timelapse/spherex_wiseview.gif` mostra três visitas
observacionais dentro de dois períodos completos de seis meses; cada frame é
uma combinação das exposições daquela visita. A faixa espectral D6 mais comum
entre os períodos fica perto de 4,885 µm. Ela foi escolhida porque os dados do
primeiro semestre não cobrem 4,6 µm (o centro aproximado da banda W2 no exemplo).
Assim, o GIF segue a mesma ideia visual do WiseView, mas usa a banda SPHEREx com
comprimentos de onda comparáveis entre as épocas. O relatório, as épocas, as
URLs e as imagens baixadas ficam em `outputs/timelapse/` e
`data/timelapse_fov176as/`. Dos 40 FITS baixados, 15 entram nos três frames;
os outros 25 continuam no diretório de dados e ficaram fora do GIF para não
misturar comprimentos de onda diferentes. `outputs/timelapse/observations.csv`
lista os 40 arquivos e indica quais entram na animação. O notebook
`notebooks/10_timelapse_spherex.ipynb` mostra o GIF, as datas e os 25 arquivos
que ficaram fora.

Cada exposição é reprojetada por sobreposição de área (`reproject_exact`) na
mesma grade celeste antes da combinação ponderada pela variância. O GIF agora é
renderizado desses mosaicos por visita. Os FITS de cada época, com mapa `NHITS`,
ficam em `outputs/timelapse/mosaics/` e podem ser abertos em outros visualizadores.

Para uma visualização baseada no catálogo Gaia DR3:

```bash
uv run spherex-tracking gaia-timelapse
```

O GIF `outputs/gaia_timelapse/gaia_dr3_motion.gif` anima as posições previstas
pelos movimentos próprios catalogados durante o intervalo Gaia DR3 de 34 meses.
Não são imagens de época. No campo de 176 segundos de arco há 10 fontes G<20;
seu maior deslocamento previsto nesse período é de apenas 0,050 segundo de arco.
O catálogo e a consulta ficam em `data/gaia_timelapse/`.

## Cubo SPHEREx com 102 bandas

```bash
uv run --extra viz spherex-tracking spectral-cube data/spectral_cube/M101_irsa.fits --label M101
```

Abra `notebooks/12_cubo_102_bandas.ipynb`. O arquivo é o cubo observado de M101
disponibilizado no [tutorial IRSA](https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/),
com 102 planos de 267 × 267 pixels. M101 é outra região do céu, diferente do ponto
WiseView dos notebooks anteriores. A URL e SHA256 estão junto ao FITS em
`data/spectral_cube/M101_irsa.provenance.json`.

O processamento usa a tabela de comprimentos de onda `WCS-WAVE`, o WCS celeste
e a cobertura `NHITS`; faz a conversão para mJy/pixel, mede um espectro com
abertura e fundo em anel e calcula a imagem de 3,3 µm menos a mediana de quatro
bandas vizinhas, seguindo o tutorial. Os produtos estão em `outputs/spectral_cube/`.
O GIF `spherex_102_bands.gif` percorre todos os 102 planos, incluindo os sem cobertura
com aviso. Cada frame é uma banda espectral, não uma data. O contraste muda por
banda (percentis 5–99,5) para mostrar estruturas; as cores não comparam fluxo absoluto.
O CSV mantém as medidas em unidades físicas. O mapa PAH é exploratório e não inclui
incertezas ou confirmação de emissão.

O seletor de bandas Aladin está nos notebooks 11 e 12 e lê o campo do próprio WCS
de M101. Para processar outro cubo IRSA no mesmo formato, passe o caminho FITS
e um nome em `--label` no comando acima.

## Mapa interativo com Aladin Lite

Para explorar a mesma região com zoom e camadas sobrepostas, instale a dependência
opcional e abra o notebook:

```bash
uv sync --extra viz --extra dev
jupyter lab notebooks/11_visualizacao_ipyaladin.ipynb
```

O mapa combina um mosaico real SPHEREx de uma visita, as posições do catálogo Gaia
DR3 e uma imagem de referência DSS2. O notebook serve para inspecionar a região e
a posição dos dados. O fundo DSS2 não é do Gaia, e os marcadores Gaia não são
imagens de época; o widget não substitui o GIF temporal SPHEREx.

## Treino padrão: observações SPHEREx + Gaia, sem injeções

```bash
uv sync --python 3.12 --extra dev --extra ml --extra literature
uv run --extra ml spherex-tracking sprints
```

Abra `notebooks/08_spherex_gaia_observados.ipynb`. A biblioteca Astroquery consulta
SPHEREx pelo `astroquery.ipac.irsa.Irsa.query_sia` e Gaia DR3 pelo
`astroquery.gaia.Gaia.launch_job`. Os FITS observados já baixados são reutilizados,
com IDs verificados contra o resultado IRSA. URLs e hashes ficam no relatório.
Os catálogos ficam em `data/catalogs/` e os resultados em `outputs/observed/`.

A versão inicial continha 720 exemplos observados: 215 observações de fontes
associadas ao Gaia e 505 picos com indicação instrumental nos flags dos FITS.
Não há exemplos injetados. As identificações Gaia são propagadas por movimento
próprio até a época SPHEREx. A seleção positiva exige contraparte isolada a até
2 arcsec, G<18,5 e núcleo limpo; a negativa exige um flag de contaminação
selecionado e nenhuma contraparte Gaia a até 6,15 arcsec. Ausência no Gaia
sozinha **não** rotula uma fonte como artefato.

Este classificador compara fontes observadas com contaminação instrumental na
imagem nativa. Não é um classificador estrela/asteroide nem um real/bogus de
resíduos DIA com eventos confirmados. Tanto o treino quanto a inferência usam
características dos mesmos pixels nativos, evitando misturar esses domínios.
O movimento é analisado depois pelo pipeline de ligação entre épocas.

Flags, identificação Gaia e coordenadas não entram nas características. A mesma
identidade Gaia ou coordenada de defeito do detector fica no mesmo grupo de
partição, para separar identidades entre treino e teste. O arquivo
`observed_training_samples.csv` registra a origem de cada rótulo para auditoria.
Os rótulos são supervisionados por catálogo/qualidade, não por revisão humana de
asteroides. As métricas avaliam essas duas populações observadas.

O limite de treinamento continua sendo 120 s, com interrupção forçada. Para
reutilizar o modelo sem treinar:

```bash
uv run --extra ml spherex-tracking sprints --reuse-training
```

O comando equivalente é `spherex-tracking observed`. O caminho padrão gera apenas
visualizações e dados observados; não inclui a animação ou o empilhamento
artificial de controle. O notebook 07 é histórico. O experimento com injeções
continua disponível somente pela opção explícita `--synthetic-controls`.

## Experimento histórico com injeções (opcional)

```bash
uv sync --python 3.12 --extra dev --extra ml --extra literature
uv run --extra ml spherex-tracking sprints --synthetic-controls
```

Abra `notebooks/07_classificacao_objetos_moveis.ipynb`. O comando usa os produtos
ZOGY existentes e entrega o classificador, ranking, associações de posição,
tracklets, comparação de velocidades, empilhamentos e animações em
`outputs/sprints/`. Para refazer só o ranking/movimento sem treinar de novo:

```bash
uv run --extra ml spherex-tracking sprints --synthetic-controls --reuse-training
```

**Treinamento curto:** XGBoost em CPU com duas threads, até 200 rodadas e parada
antecipada. Um processo pai limita a execução a **120 segundos**, incluindo
importações e construção das matrizes. Se exceder, encerra o processo de treino,
registra `timeout` e usa um ranking heurístico explicitamente identificado.
O CLI aceita `--train-timeout` até 120 s e `--samples` para mudar o tamanho do
conjunto. A versão instalada é `xgboost-cpu`, sem dependências CUDA.

O campo ainda não possui rótulos humanos de eventos confirmados. Por isso o treino
usa 900 exemplos conhecidos: fontes e artefatos artificiais acrescentados aos
fundos reais e processados pelo ZOGY. Inclui pixel quente, dipolo, rastro, fonte
estendida, ringing e artefatos pontuais difíceis de distinguir de uma fonte.
Não rotulamos automaticamente os candidatos reais como negativos.

Extraem-se 14 características: intensidade do escore, pico e mínimo da diferença,
ruído local, fração positiva, balanço positivo/negativo, correlação e resíduo de
ajuste da PSF, largura, alongamento, assimetria, concentração e proximidade de
máscara. Coordenadas, tipo injetado e grupo espacial ficam fora das entradas.
Regiões do céu distintas são reservadas para treino, parada antecipada e teste;
versões aumentadas da mesma região não passam de um conjunto para outro.

As classes previstas são `fonte_candidata` e `provavel_artefato`. A pontuação
aprendida não é a probabilidade de ser asteroide. `review_labels.csv` permite
anotar rótulos para uma próxima versão supervisionada. As métricas de teste
descrevem os controles artificiais em regiões reservadas, não objetos reais
confirmados nem outros campos do céu. O ranking final combina 70% da pontuação
do modelo, 20% de suporte temporal e 10% de intensidade do sinal.

Na Sprint 3:

- Cross-match esférico compara RA/Dec com as fontes SEP da primeira exposição.
  Uma coincidência de posição não é identificação de objeto.
- Resíduos positivos pertencem à época da imagem nova; negativos à época da
  referência. Aparições repetidas da mesma posição/época são fundidas.
- Tracklets usam ao menos três épocas distintas dentro de cada grupo temporal.
  Ligações por posição no intervalo completo usam ao menos quatro épocas.
- Velocity matching compara tracklets de grupos diferentes, com tolerância que
  considera a curta duração de cada grupo. Ligações diretas também ajustam uma
  velocidade comum e rejeitam resíduos acima de 1,25 pixel. Velocidades globais
  vão de 0,5 a 12 pixels/hora. Durações curtas não resolvem bem velocidades.
- A sequência atual tem oito épocas em 1,71 h, dois grupos de quatro imagens e
  um intervalo de cerca de 90 minutos entre grupos. O Shift-and-Stack é tentado
  em até cinco trajetórias com deslocamento mensurável e cobertura do recorte.
  O escore inclui o modelo de referência compartilhada; a imagem é ilustrativa.

Arquivos principais: `candidate_ranking.csv`, `review_labels.csv`,
`training_metrics.json`, `positional_crossmatches.csv`, `tracklets.json`,
`velocity_matches.json`, `tracks.json`, `stacks.npz`, `ranking.png`, `tracks.png`,
`stack_comparison.png`, `candidate_blink.gif` e `control_blink.gif`.
A animação de controle identifica explicitamente a fonte artificial. Os dados
reais mostram hipóteses para revisão; não há associação orbital automática.

## Pipeline SEP + astrometria + PSF matching + ZOGY

```bash
uv sync --python 3.12 --extra dev --extra literature
uv run spherex-tracking zogy
```

Abra `notebooks/06_sep_astrometria_psf_zogy.ipynb`. O pipeline usa os mesmos oito
FITS reais já baixados. Catálogos SEP por exposição, mapas, figura e relatório
ficam em `outputs/zogy/`. O padrão faz 128 ensaios nulos e nove injeções; os
controles são identificados separadamente dos dados reais sem injeção.

**Correção de máscara:** a versão anterior rejeitava todos os flags não nulos,
incluindo SOURCE (bit 21), que identifica fontes conhecidas e não defeitos.
Isso retirava estrelas necessárias para verificar astrometria e medir PSFs.
Agora `quality.bad_pixel_mask` preserva SOURCE isolado e rejeita os demais flags
ou combinações, conforme a Tabela 16 do
[Explanatory Supplement v2.1](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf).
O notebook 05 foi reexecutado com essa correção. Os resultados armazenados nos
notebooks 03 e 04 são históricos e precisam ser reexecutados para comparação
numérica com o pipeline atual; seus comandos já usam a máscara corrigida.

As etapas executadas são:

1. **SEP:** estimação de fundo, fontes com limiar 4σ, posições e fotometria de
   abertura em pixels nativos. Os catálogos completos ficam em ECSV.
2. **Astrometria relativa:** WCS do primeiro FITS como referência, associações
   mútuas de fontes e ajuste de translação com metade das estrelas. A outra
   metade avalia a correção; se o RMS piora, preserva-se a WCS original.
   Esse RMS é dos centroides transformados, antes da quantização do registro.
   Não é uma validação absoluta independente com Gaia. As imagens são
   registradas por amostra nativa mais próxima, descartando duplicatas.
3. **PSFs calibradas e matching:** seleciona a zona EPSF usando as coordenadas
   do detector original e o oversampling dos cabeçalhos, seguindo o
   [tutorial oficial](https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/).
   A ePSF já é convolvida pelo pixel: é amostrada, não integrada novamente.
   A convolução cruzada N⊗Pr e R⊗Pn testa um matching independente.
4. **ZOGY:** implementação própria das equações 13–17 e 25–30 de
   [Zackay, Ofek & Gal-Yam (2016)](https://arxiv.org/abs/1601.02655).
   O ZOGY recebe cada imagem e sua própria PSF, realizando a combinação em
   Fourier. Não se alimenta o algoritmo com as imagens já convolvidas, pois
   isso alteraria a hipótese de ruído de entrada. São gravados D, S e S_corr;
   S_corr propaga mapas de variância e uma aproximação do erro astrométrico.
5. **Candidatos:** SEP nos resíduos positivos e negativos de S_corr acima de
   5σ nominais, mais associações exploratórias de movimento e dipolos.
   Vários pares compartilham exposições; contagens não são objetos independentes.
6. **Estatística:** limite de Bonferroni, 128 máximos globais sob ruído gaussiano
   com dependências entre pares preservadas, intervalo binomial da taxa de
   excedência e injeções de SNR nominal 3, 5 e 8 em três posições fixas.
   Uma detecção que já existia no fundo não conta como recuperação da injeção.

O teste nulo é **condicional** às variâncias, máscaras, PSFs e escalas ajustadas.
Ele não simula erros de modelo de céu, cor ou PSF, nem mede pureza no céu real.
A dispersão de S_corr e as diferenças espectrais são reportadas separadamente:
um valor alto de S_corr não estabelece a identificação de um asteroide.

São comparados quatro pares com longa separação temporal e quatro pares de
comprimentos de onda vizinhos. Os primeiros favorecem deslocamentos mensuráveis,
mas têm maior diferença espectral LVF; os segundos têm apenas cerca de dois
minutos de intervalo e podem subtrair quase todo o sinal de um objeto lento.
As bandas não são assumidas equivalentes. Uma única ePSF e fase central por
recorte, resampling por pixel próximo e máscaras aproximadas de FFT continuam
sendo limitações. As injeções têm SNR nominal constante, não um espectro físico.

## Execução em dados reais SPHEREx

```bash
uv run spherex-tracking real
```

Esse comando consulta o serviço SIA2 oficial, baixa oito recortes DR1 do detector 1
na região RA=134,6917°, Dec=16,0303°, observada em 31/10/2025, e executa uma busca
de trajetórias entre −8 e +8 pixels/hora em cada componente. Os FITS são reais,
sem fontes móveis injetadas, e são reutilizados nas próximas execuções.

Abra `notebooks/03_spherex_real.ipynb` para ver a figura e o relatório.
Os produtos ficam em `outputs/spherex/`; os FITS e as URLs de origem ficam em
`data/spherex/manifest.json`. Os recortes de 0,25° preservam os metadados dos
produtos originais de 2040 × 2040 pixels.

A busca usa WCS para transformar cada trajetória em coordenadas nativas e amostra
os filtros de PSF nos pixels inteiros mais próximos. Assim, o cálculo do escore
não interpola o ruído das imagens. São subtraídos ZODI e uma mediana residual;
os flags de qualidade (exceto SOURCE) e pixels muito brilhantes são mascarados.

Esta execução é exploratória: usa PSF gaussiana provisória, não ajusta as ePSFs
fornecidas e ainda não verifica o espectro do objeto. Os comprimentos de onda
registrados no relatório vêm de WCS-WAVE e servem apenas para inspeção.
A análise científica requer CWAVE/CBAND. Os candidatos e escores não representam
asteroides confirmados: faltam associação a efemérides, validação em subconjuntos
independentes e controle empírico de falsos positivos.

## Diferenciação de imagens

```bash
uv run spherex-tracking difference
```

Abra `notebooks/05_image_differencing.ipynb`. São usadas as mesmas oito exposições
reais SPHEREx DR1. Os produtos ficam em `outputs/differencing/`: figura, relatório
e NPZ com referências, diferenças, variâncias, máscaras e épocas.

Esta implementação é uma referência inicial de **image differencing**:
registra as imagens por WCS, subtrai ZODI e uma mediana de fundo, e forma uma
referência para cada imagem a partir da média ponderada das outras sete.
A imagem testada fica fora de sua referência. O registro usa o pixel nativo mais
próximo e rejeita amostras duplicadas, evitando interpolar o ruído ou contar duas
vezes um mesmo pixel de uma exposição. A quantização da PSF continua presente.

Não implementa ZOGY, Alard-Lupton ou Bramich e ainda não ajusta um kernel de PSF
ou uma escala fotométrica entre exposições. Para contexto sobre esses métodos,
veja [Alard & Lupton (1998)](https://arxiv.org/abs/astro-ph/9712287) e
[Zackay, Ofek & Gal-Yam (2016)](https://arxiv.org/abs/1601.02655).
Os comprimentos de onda LVF diferentes são uma limitação do modelo de céu fixo.

As referências são compartilhadas: não se deve simplesmente empilhar as diferenças
tratando seus ruídos como independentes. O escore de trajetória elimina uma cena
estacionária comum por pixel e calcula a informação restante do modelo de fonte
móvel. Para pesos `w=1/V` e PSF móvel `P`:

```text
P_centrado = P - Σ_épocas(w P)/Σ_épocas(w)
informação = Σ(w P_centrado²)
escore = Σ(w P_centrado I)/sqrt(informação)
```

Isso inclui a covariância da referência e a perda de sinal da própria fonte na
subtração, sob as hipóteses de ruído diagonal, céu estacionário e PSF conhecida.
Não corrige automaticamente erros do modelo, ruído instrumental correlacionado
ou diferenças de cor entre fontes.

A busca gera até 100 propostas com um filtro simples e depois as reordena pelo
escore que inclui essa covariância. Não é uma busca exaustiva da verossimilhança.
Os controles acrescentam fontes de SNR nominal 3 e 5 sobre as imagens reais já
registradas, mantendo máscaras fixas e escolhendo posições com boa cobertura.
A referência é reconstruída com a injeção em todas as épocas: assim, o teste
inclui a remoção parcial do próprio objeto e seus resíduos negativos.

O relatório distingue medição forçada na trajetória verdadeira de recuperação
cega. Dois controles favoráveis não medem completude ou taxa de falsos positivos.
Os testes automatizados verificam também a escala do escore sob ruído gaussiano
independente, incluindo a referência compartilhada.

## Comparação dos dois artigos adicionais

```bash
uv sync --python 3.12 --extra dev --extra literature
uv run --extra literature spherex-tracking papers
```

Os experimentos usam os oito FITS reais já baixados, sem novos downloads.
Os relatórios, catálogos e logs ficam em `outputs/literature/`. Abra
`notebooks/04_comparacao_artigos.ipynb` depois de executar o comando.

- **Gural, Otto e Tedesco (2018)**,
  [Moving Object Detection Using a Parallax Shift Vector Algorithm](https://doi.org/10.1088/1538-3873/aac1ff):
  implementação independente das equações 1–2, com busca de distância uniforme
  em distância inversa (seção 2.3), comparada ao caso linear. O
  [repositório NASA SALTAD](https://github.com/NASA-Planetary-Science/SALTAD)
  disponibiliza instruções e formulários de solicitação, não o código executável.
  Este experimento não executa SALTAD/TGEN nem reproduz todo o pipeline do artigo.
- **Stetzler et al. (2025)**,
  [An Efficient Shift-and-Stack Algorithm Applied to Detection Catalogs](https://arxiv.org/abs/2509.26279v1):
  execução da implementação dos autores, `find-asteroids`, em CPU, incluindo
  Hough, regressão robusta MCD e coleta dos pontos próximos da trajetória.
  Os catálogos vêm de máximos locais do filtro de PSF nas imagens reais, com
  limiares de SNR 2, 3 e 5. A grade respeita Δv ≤ Δx/Δt (equação 16).

Para Gural são lidos X_SC/Y_SC/Z_SC nos meios das exposições. É somada a posição
baricêntrica da Terra da efeméride integrada do Astropy. O cabeçalho identifica a
origem como GEOCENTER, mas não especifica integralmente os eixos: o experimento
assume eixos equatoriais inerciais alinhados com ICRS. Essa hipótese precisa ser
verificada antes de usar os resultados como astrometria científica. Não há
correção de tempo de luz, aberração ou busca em velocidade radial.

Os controles de injeção acrescentam uma fonte artificial sobre o fundo real com
a máscara de entrada preservada. A posição é escolhida por boa cobertura e baixo
ruído, não pelo sinal observado: é um caso favorável, não uma medida de completude.
O controle de Gural tem paralaxe; o de Stetzler é linear, conforme seu modelo.
A busca não recebe a trajetória injetada; a comparação com a verdade ocorre depois.

Votos Hough não são SNR. Vários votos podem vir da mesma exposição: o relatório
também conta épocas distintas e exige quatro para indicar um candidato a revisão.
Isso não confirma um objeto astronômico. Os tempos dos catálogos de diagnóstico
são dias relativos com origem arbitrária, usados pela API CPU; não são MJD para
alimentar diretamente o CLI externo dos autores.

Os tempos medidos são das etapas de busca, com JIT no caso do primeiro catálogo.
Não reproduzem os ganhos de velocidade ou a profundidade publicados no DECam.
O modelo de PSF e as diferenças espectrais LVF continuam sendo limitações.

## Executar

Com [uv](https://docs.astral.sh/uv/):

```bash
uv sync --python 3.12 --extra dev
uv run spherex-tracking demo
uv run pytest
```

O ambiente fica em `.venv`. No VS Code, selecione `.venv/bin/python` como
interpretador e kernel dos notebooks. O Python de sistema não é alterado.

A demonstração grava em `outputs/demo/`:

- `comparison.png`: uma exposição e empilhamentos com e sem movimento;
- `report.json`: trajetória estimada, SNR, erros e máximos da busca nos controles;
- `experiment.npz`: imagens, épocas, variâncias, máscaras e empilhamento.

O padrão executa oito campos de controle independentes com estrelas e sem objeto
móvel. Para aumentar a amostra:

```bash
uv run spherex-tracking demo --seed 42 --null-trials 100 --output outputs/control100
```

Oito controles são apenas uma verificação inicial. A fração de cauda com correção
de uma contagem tem resolução mínima de 1/(N+1); não é significância de descoberta.
Repetir injeções em posições, velocidades, fluxos e campos diferentes será necessário
para medir completude e falsos positivos da população.

## O que está implementado

1. Subtração de uma mediana de fundo por exposição.
2. Máscara de estrelas brilhantes baseada na mediana temporal, preservando máscaras
   de entrada; pixels rejeitados recebem peso zero.
3. Busca cega em duas componentes de velocidade com filtro de PSF e variância.
4. Refinamento local de posição e velocidade, ajustando PSFs nos pixels originais.
5. Empilhamento com pesos, mapa de variância e cobertura, sem circular as bordas.
6. Recuperação de injeção e comparação com campos de controle pela mesma busca.
7. Inspeção de metadados FITS, sem interpretar canais espectrais como épocas.

O núcleo está em `src/spherex_tracking/core.py`. As coordenadas são base zero:
`x` é coluna, `y` é linha, e as velocidades são **pixels por hora**, sem conversão
automática para ascensão reta ou declinação. A posição do candidato corresponde
à mediana das épocas fornecidas, que representam os meios das exposições.

## Estatística usada

Para uma trajetória, `D` representa os pixels com fundo subtraído, `P` a PSF
normalizada à unidade e `V` a variância por pixel. Somando nas exposições e pixels:

```text
A = Σ(P D / V)
B = Σ(P² / V)
fluxo estimado = A / B
SNR = A / sqrt(B)
```

É um ajuste de amplitude comum com ruído gaussiano independente e variâncias
conhecidas. Com exposições equivalentes, produz o ganho ideal de raiz de N.
A busca inicial arredonda deslocamentos para pixels inteiros. O refinamento ajusta
PSFs subpixel diretamente às imagens, sem interpolar o ruído. O empilhamento
gravado é uma visualização com deslocamentos arredondados; seu pico não define
o SNR reportado.

O SNR de um candidato otimizado em milhares de posições e velocidades **não** é
uma significância global. Por isso, o relatório compara com máximos obtidos
repetindo a busca e o refinamento nos campos nulos.

## Relação com o artigo

As seções 3.2.1–3.2.3 motivam remoção de fontes estacionárias, busca em velocidades
e refinamento. A seção 4.3 motiva o teste com um objeto abaixo do limiar individual.
O artigo usa SNR e alongamento no refinamento. Aqui usamos uma maximização local
do SNR por PSF: é uma adaptação de engenharia, não uma reprodução exata.
Ainda não implementamos o critério de alongamento nem reproduzimos seus dados.

## Inspecionar dados reais

```bash
uv run spherex-tracking inspect /caminho/arquivo.fits
uv run spherex-tracking inspect data/raw
```

Os notebooks `notebooks/01_inspecao_dados.ipynb` e
`notebooks/02_shift_and_stack.ipynb` permitem inspecionar arquivos e explorar o
experimento. O primeiro funciona sem dados locais e informa quando não os encontra.

Segundo a [documentação oficial dos produtos SPHEREx](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-products/),
as imagens espectrais Level 2 incluem `IMAGE`, `FLAGS`, `VARIANCE`, `ZODI`,
`EPSF` ou `PSF`, e `WCS-WAVE`. Os cubos all-sky possuem eixo espectral e não
substituem uma sequência de exposições. As especificações dependem do release.
`VARIANCE` já é variância; não deve ser elevada ao quadrado outra vez.

Antes de alimentar o núcleo com SPHEREx, precisamos verificar a sobreposição
espacial, as épocas e a cadência reais, a calibração astrométrica e fotométrica,
os bits de `FLAGS` e a compatibilidade espectral ao longo da trajetória.
Os filtros LVF fazem o comprimento de onda depender da posição no detector;
estar no mesmo detector não garante a mesma banda efetiva. CWAVE/CBAND dos
produtos de calibração são a referência para análise científica.

O núcleo exige imagens previamente registradas numa grade comum e medidas
comparáveis. **O comando `inspect` não registra nem empilha arquivos reais.**
A reprojeção também pode correlacionar o ruído e exigirá tratamento explícito.

## Limites desta versão

- Movimento linear e velocidade constante numa janela curta.
- PSF gaussiana constante, fonte sem rastro dentro de cada exposição e fluxo constante.
- Ruído gaussiano independente; sem modelo completo de ruído instrumental ou fótons da fonte.
- Fundo escalar e máscara temporal simples: objetos muito lentos podem ser mascarados.
- Sem consulta de efemérides, validação astrométrica, PSF espacial ou adaptação LVF.
- Uma injeção recuperada não estabelece completude, pureza ou descoberta de asteroide.

O próximo marco é selecionar exposições reais de uma região comum e medir sua
cadência e resposta espectral antes de definir a adaptação ao SPHEREx.

## Referências técnicas

- [Astropy FITS](https://docs.astropy.org/en/stable/io/fits/): leitura de HDUs e cabeçalhos.
- [SciPy ndimage.convolve](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.convolve.html): filtro ponderado por PSF.
- [SciPy optimize.minimize](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize.html): ajuste local da trajetória.
- [SPHEREx: acesso oficial](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/): serviços e interfaces de consulta.
