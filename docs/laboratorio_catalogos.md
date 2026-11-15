> Legacy UI references below describe the earlier prototype. The home is `web/site` at `/`; the current laboratory is `web/sky-explorer` at `/lab`.

# Preparar observações: MPC e amostras cruzadas

O laboratório foi incorporado à branch `dessinha` preservando o coletor, notebooks,
configurações e página de clima já existentes. A interface está em `web/infrared-mask`;
o servidor e processamento ficam em `src/spherex_tracking/infrared*.py`.

## Executar

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-infrared.txt
.venv\Scripts\python.exe scripts/infrared_lab.py calibration --detector all
.\start-infrared.ps1
```

Abra **http://127.0.0.1:8766/lab**. Para escolher outra porta:
`./start-infrared.ps1 -Port 8771`. O servidor escuta apenas em `127.0.0.1` e deve
permanecer aberto enquanto o laboratório estiver em uso. As calibrações D1–D6 são
armazenadas em `data/infrared/calibrations` (aproximadamente 200 MB no total).

## Fluxo na aba Preparar observações

1. Informe um nome ou designação e clique em **Buscar no Minor Planet Center**.
   O servidor consulta a API oficial de identificação por GET com corpo JSON
   `{"ids": ["identificação"]}`. Se houver ambiguidade, escolha um resultado.
   Identidades são novamente validadas antes da aquisição; falhas MPC são explícitas.
   A resposta e sua proveniência ficam em cache local por até um dia.
2. Escolha **Trajetória do objeto MPC · MOST** para consultar exposições junto às
   posições previstas, ou uma amostra da análise carregada para buscar imagens
   naquelas coordenadas ICRS. A primeira análise fornece as amostras selecionáveis;
   relatórios anteriores também podem oferecer amostras, sem inventar dados WISE.
3. Escolha um dos **102 canais SPHEREx**, ou uma janela livre. Um canal define detector
   e intervalo espectral no servidor; alterar limites/detector manualmente volta à
   janela livre. A escolha de uma amostra sugere seu canal, dia inicial e dia seguinte.
4. Mantenha **Cruzar Gaia DR3 + AllWISE / NEOWISE** habilitado para buscar o contexto
   WISE nas regiões observadas. Gaia é consultado para a máscara e astrometria mesmo
   quando a aquisição de contexto WISE está desligada.
5. Solicite o processamento. A seção **Amostras cruzadas** mostra cobertura e estado
   das consultas. Selecionar uma amostra oferece WISEView e, havendo associação
   AllWISE e sobreposição espectral, os links para recortes FITS W1/W2 correspondentes.

**Busca por amostra é uma busca de campo fixo.** Usa RA/Dec armazenados no relatório,
selecionados por ID; o cliente não fornece coordenadas arbitrárias. Consulta as duas
coleções públicas `spherex_dr1` e `spherex_qr3` pelo SIA2, com posição, período e janela
espectral. Cada FITS é conferido pelo WCS e pela calibração CWAVE/CBAND. Essas posições
são rotuladas `fixed_sky_not_moving_ephemeris`; não são a trajetória do objeto MPC
em outras épocas. Para seguir o objeto, escolha o modo MOST.

## Merge orientado pelo SPHEREx

A tabela de referência é `spherex_channels.json`, extraída de `SPECTRAL_CHANNELS` do
cubo oficial M101/IRSA, com URL e SHA-256 do FITS de origem. Contém as 102 posições
espectrais, 17 por detector. Não foi criada por interpolação de seis bandas.
Os canais 51 e 52 permanecem na tabela: são posições sem dados no produto all-sky,
e sua presença não significa que existam medidas.

Cada amostra coberta do alvo ou do catálogo Gaia tem exposição, época UTC/MJD, RA/Dec,
detector, CWAVE e canal. A associação nominal ao canal usa o centro mais próximo
cujo intervalo oficial contém CWAVE, dentro do detector correto. Não substitui o
mapa geométrico de canais do detector nem a calibração contínua CWAVE/CBAND.
A aquisição de um canal exige também que o centro calibrado na posição selecionada
seja atribuído àquele canal. Aberturas continuam usando os pixels nativos aceitos.

O cruzamento é uma associação à esquerda: todas as amostras SPHEREx cobertas ficam
preservadas, inclusive sem contraparte externa. O raio de candidatos é 3″:

- **Gaia DR3:** posições propagadas à época SPHEREx com os movimentos próprios
  disponíveis; fornece contexto astrométrico e contaminação estelar, não fluxo IR.
- **AllWISE:** candidatos posicionais mantêm identificação, magnitudes W1/W2,
  `cc_flags` e `ph_qual`. O `coadd_id` oficial gera o caminho de imagem e o recorte
  pelas coordenadas da amostra. Imagens WISE têm sua unidade original, frequentemente
  DN, e não são subtraídas nem comparadas numericamente com o SPHEREx em MJy/sr.
- **NEOWISE:** preserva identificador de exposição/fonte e MJD. Só marca
  `epoch_compatible=true` se a diferença para a época SPHEREx for de até um dia.
  Candidatos históricos continuam rotulados como contexto de outra época.
- **WISEView:** é um link para explorar as imagens daquele campo; não é apresentado
  como um catálogo adicional de medições independentes.

As janelas aproximadas W1=2,8–3,8 µm e W2=4,1–5,2 µm selecionam contexto por
sobreposição com o canal SPHEREx. Não equivalem a curvas de resposta nem tornam
uma magnitude WISE um fluxo de banda estreita. Registros WISE não são propagados
por movimento próprio; associações permanecem `positional_context_not_identity`.
Nenhuma associação confirma um objeto móvel. Não são usadas bandas fora do IR.

Aquisição limitada: cones de 0,09°, até 2.000 registros por catálogo/cone e três
consultas simultâneas; resultados no limite são marcados como truncados/parciais.
As amostras incluem até 100 fontes Gaia por exposição e até 20 candidatos externos
por amostra/catálogo. Limites e exposições truncadas ficam nos metadados.
Falhas não geram dados sintéticos nem preenchem canais sem cobertura.

## Produtos e APIs locais

- `report.json`: acrescenta `dataset_join`, `request_selection` e identidade/proveniência MPC.
- `joined_samples.json`: canais, amostras, candidatos, separações, épocas, filtros,
  links de imagens, estado e proveniência das consultas. Também disponível em relatórios antigos.
- FITS, CSV de fotometria e mosaicos coloridos mantêm o processamento descrito em
  [Máscara infravermelha](infrared_mask.md) e [Mosaico estético](infrared_color.md).
- `GET /api/channels`: tabela oficial de 102 canais.
- `GET /api/mpc?object=1766`: consulta de identidade e possíveis escolhas.
- `POST /api/run`: aceita adicionalmente `channel_id` (0–102), `sample_id` e
  `include_context` (booleano). Uma amostra inexistente é rejeitada antes da aquisição.

CLI: `scripts/infrared_lab.py archive --channel-id 65 --max-exposures 4`.
Manifestos locais continuam reproduzíveis sem rede; `context_catalogues` pode conter
catálogos já adquiridos, enquanto sua ausência produz associações externas vazias.

## Validação

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-infrared.txt
.venv\Scripts\python.exe -m pytest -q
npm --prefix web/sky-explorer test
npm --prefix web/sky-explorer run build
```

Em 15/11/2026, MPC resolveu 1766 como Slipher. Uma consulta espacial de teste retornou
62 exposições SPHEREx QR3. A seleção de uma amostra real e do canal 55 baixou e processou
um FITS compatível. Um recorte AllWISE W1 de 315 × 315 pixels foi validado pelo WCS.
O fluxo completo das 12 exposições gerou 268 amostras em 15 canais, com 85 amostras
associadas ao AllWISE e 41 ao NEOWISE. O NEOWISE ficou parcial por limite de resultados;
as 12 medidas de abertura permaneceram iguais às da análise anterior.

Referências primárias:

- [API de identificação MPC](https://docs.minorplanetcenter.net/mpc-ops-docs/apis/query-identifier/)
- [Produtos e canais SPHEREx](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
- [Acesso SPHEREx e coleções](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/)
- [Consulta aos catálogos IRSA](https://irsa.ipac.caltech.edu/onlinehelp/catalogs/catalogs/api.html)
- [Caminhos e recortes AllWISE](https://irsa.ipac.caltech.edu/ibe/docs/wise/allwise/p3am_cdd/)
- [Janelas instrumentais WISE](https://wise2.ipac.caltech.edu/docs/doc_tree/sdl_reports/sdl09-157-focus.pdf)
