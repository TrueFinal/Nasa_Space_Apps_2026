# Earth Detectives — The ENSO Case

Ingestão de dados científicos do MVP NASA Space Apps 2026. Esta entrega cobre
coleta, proveniência e auditoria técnica. O documento de referência está em
[`docs/earth_detectives_enso.pdf`](docs/earth_detectives_enso.pdf).

## Instalação

Python 3.12 recomendado. Com [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-lock.txt
```

Alternativa com Python 3.12 já instalado:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

`requirements-lock.txt` registra as versões verificadas no ambiente Linux/Python
3.12, incluindo ferramentas de desenvolvimento. `requirements.txt` declara somente
as dependências de execução, para instalação com resolução própria.

## Primeira execução pública: NOAA

```bash
.venv/bin/python scripts/fetch_mvp_data.py --datasets noaa_roni
```

Baixa a série oficial completa e o HTML da classificação de episódios. Não calcula
fases próprias, não filtra ou altera a fonte e não reconstrói o RONI com MUR.
Reexecute para conferir SHA-256 e reutilizar arquivos. Use `--refresh` para consultar
nova revisão, preservando snapshots anteriores por nomes com hash.

## NASA: planejar antes de transferir

```bash
.venv/bin/python scripts/fetch_mvp_data.py \
  --start 2015-12-01 --end 2015-12-02 --dry-run
```

O modo dry-run consulta apenas metadados públicos CMR e Harmony, valida nomes e
versões e grava o plano em `data/metadata/latest_run.json`. Não submete jobs nem
baixa arquivos científicos. O fim é limitado ao último grânulo catalogado; a
consulta deve ser refeita, pois coleções e disponibilidade mudam.

Para autenticar, copie `.env.example` para `.env` e preencha `EARTHDATA_TOKEN` com
um token da sua conta em https://urs.earthdata.nasa.gov/. Configure localmente e
autorize as aplicações NASA solicitadas pelo provedor. Nunca envie tokens por
mensagem ou os inclua no Git. O coletor aceita também a variável de ambiente;
variáveis já definidas têm precedência sobre `.env`. Não há prompt interativo.

Primeiro teste mensal, de baixo volume:

```bash
.venv/bin/python scripts/fetch_mvp_data.py \
  --datasets gpm_monthly gldas merra2 \
  --start 2015-12-01 --end 2015-12-31
```

Primeiro teste diário e camada oceânica opcional:

```bash
.venv/bin/python scripts/fetch_mvp_data.py \
  --datasets gpm_daily --start 2015-12-01 --end 2015-12-02
.venv/bin/python scripts/fetch_mvp_data.py \
  --datasets mur_sst --start 2015-12-01 --end 2015-12-02 --dry-run
```

Produtos disponíveis: `noaa_roni`, `gpm_daily`, `gpm_monthly`, `gldas`, `merra2`,
`mur_sst`. MUR exige seleção explícita. Os produtos IMERG configurados são Final
V07; não há fallback automático para NRT.

Sem datas, a CLI propõe a janela comum das coleções NASA descobertas, mas a execução
recusa datasets com mais de 50 grânulos. Para um histórico maior, confirme primeiro
o dry-run e aumente `--max-granules`; `0` remove explicitamente o limite. Não há
truncamento para os primeiros 50 arquivos. A contagem não comprova continuidade.

`--wait-seconds 120` limita a espera por job. Um job pendente fica registrado no
manifesto; reexecute o mesmo comando para retomar o polling. Jobs falhos, pausados
ou expirados exigem revisão em https://harmony.earthdata.nasa.gov/; `--refresh`
solicita novos jobs. Em timeout na **submissão**, confira os jobs da conta antes de
reexecutar: a resposta pode ter se perdido após o servidor aceitar o trabalho.
Downloads incompletos são descartados e reiniciados, sem retomada por byte.

## Regiões e seleção temporal

Edite `config/regions.yaml`. Niño 3.4 usa [-170,-5,-120,5] em EPSG:4326.
IMERG e GLDAS usam por padrão `brasilia_smoke`: caixa provisória de 1° para testes
de transferência terrestre. **Não é uma área de estudo aprovada nem uma bacia**.
MERRA-2 e MUR usam Niño 3.4. `--region ID` substitui a região dos produtos NASA
selecionados; GLDAS recusa região declarada oceânica.

Para polígono, crie uma entrada com `crs: EPSG:4326` e
`geometry_file: minha_bacia.geojson`, relativa ao YAML. Aceita Polygon/MultiPolygon
ou Feature com essa geometria. O envelope é extraído pelo provedor; a geometria e
seu hash ficam no manifesto. **Não é aplicada máscara do polígono**. Não há suporte
a regiões cruzando o antimeridiano: divida-as em entradas separadas.

A seleção temporal usa grânulos que intersectam o período inclusivo solicitado.
Cada grânulo mantém seus tempos nativos completos: uma observação mensal não é
transformada em observação de dois dias. Isso pode incluir registros ou cobertura
de tempo além das datas pedidas. O manifesto distingue intervalo solicitado,
intervalo de consulta, cobertura do grânulo e tempos encontrados no arquivo.
Nenhuma média, conversão de unidades, máscara, interpolação ou limpeza é aplicada.

## Arquivos e inventário

- `data/raw/<dataset>/<produto>/<região>/`: originais NOAA e recortes NASA do provedor.
- `data/metadata/manifest.json`: proveniência por arquivo, hashes, auditoria e jobs.
- `data/metadata/*_discovery.json`: metadados oficiais de coleção e capacidades.
- `data/metadata/latest_run.json`: plano, resultados e falhas da última execução.
- `data/metadata/inventory.json`: tamanho, variáveis, unidades, dimensões, tempos,
  ausências e integridade dos arquivos efetivamente obtidos.
- `data/metadata/dataset_catalog.csv`: inventário por arquivo.
- `logs/ingestion.log`: tentativas e falhas sem credenciais/queries assinadas.

Dados e logs ficam fora do Git. Horários de coleta são registrados em UTC e
America/Sao_Paulo; não são a data da observação. Metadados ainda desconhecidos
ficam nulos. A auditoria lê as variáveis solicitadas para detectar corrupção e
ausências, sem interpretar tendências ou causalidade.

```bash
.venv/bin/python scripts/fetch_mvp_data.py --inventory-only
```

Saída: código `0` indica sucesso; `1` indica falha parcial de dataset ou problema
de integridade no inventário; `2` indica configuração/manifesto inválido ou falha
de disco. Falhas NASA não impedem a coleta pública NOAA. Use um único processo
por diretório de saída; o manifesto não implementa escrita concorrente.

## Verificação e acompanhamento

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check earth_detectives scripts tests
```

Os testes usam respostas controladas e NetCDF sintético em pastas temporárias;
não comprovam uma coleta autenticada NASA. Os resultados reais e limitações estão
em [`docs/diario_execucao.md`](docs/diario_execucao.md),
[`docs/inventario_coleta.md`](docs/inventario_coleta.md),
[`docs/inventario_coleta.json`](docs/inventario_coleta.json),
[`docs/fontes_e_datasets.md`](docs/fontes_e_datasets.md) e
[`docs/decisoes_tecnicas.md`](docs/decisoes_tecnicas.md).

Branch: `feature/data-ingestion-mvp`. Commits incrementais e pushes verificados
permitem acompanhar a evolução no repositório oficial. A EDA será uma etapa conjunta
posterior à apresentação do inventário e à resolução das pendências de coleta.
