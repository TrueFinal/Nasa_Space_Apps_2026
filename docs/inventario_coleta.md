# Inventário da coleta — 2026-11-14

Estado: **coleta de amostras executada e validada**, com RONI e os quatro produtos NASA configurados (IMERG diário/mensal, GLDAS, MERRA-2 e MUR complementar). Não representa a extração de toda a janela histórica. Evidências completas: [`inventario_coleta.json`](inventario_coleta.json).

| Dataset | Arquivos | Bytes | Período/registro | Grade nas amostras |
|---|---:|---:|---|---|
| NOAA RONI + classificação HTML | 2 | 112,812 | jan/1950–set/2026; 921 trimestres + HTML | Índice Niño 3.4, sem grade |
| IMERG Final diário V07 | 2 | 71,375 | 01–02/12/2015; 2 registros diários | 11 × 11; ~0,1° |
| IMERG Final mensal V07 | 1 | 44,180 | dez/2015; 1 registro mensal | 11 × 11; ~0,1° |
| GLDAS Noah mensal 2.1 | 1 | 83,186 | dez/2015; 1 registro mensal | 4 × 4; 0,25° |
| MERRA-2 mensal 5.12.4 | 1 | 86,639 | dez/2015; 1 registro mensal | 21 lat × 81 lon; 0,5° × 0,625° |
| MUR SST 4.1 | 2 | 10,448,477 | 01–02/12/2015, às 09h; 2 registros | 1001 lat × 5001 lon; ~0,01° |

Total: **9 arquivos, 10,846,669 bytes** (10,85 MB decimais). Os arquivos brutos ficam em `data/raw/<dataset>/<produto>/<região>/`, fora do Git. O manifesto local está em `data/metadata/manifest.json`.

## Variáveis e unidades confirmadas nos arquivos

- RONI: °C conforme a definição NOAA. Série ASCII e tabela HTML originais preservadas; nenhuma fase foi inferida localmente.
- IMERG diário: `precipitation`, `mm/day`. Mensal: `Grid/precipitation`, `mm/hr`; taxa média mensal preservada, sem conversão para acumulado.
- GLDAS: quatro camadas `SoilMoi*` e `RootMoist_inst`, `kg m-2`; `Evap_tavg`, `kg m-2 s-1`; `Qs_acc` e `Qsb_acc`, `kg m-2`. São estimativas de modelo, não medições diretas em poços ou lotes.
- MERRA-2: `U10M`, `V10M`, `m s-1`; `SLP`, `Pa`; `T2M`, `K`; `TQV`, `kg m-2`. Produto de reanálise.
- MUR: `analysed_sst` e `analysis_error`, ambas `kelvin`. Dados analisados de nível 4; não substituem RONI.

## Integridade, tempo e proveniência

Todos os nove hashes SHA-256 foram conferidos. Os sete NetCDF foram abertos e todos os blocos das variáveis solicitadas puderam ser lidos. Nenhuma ausência por NaN/FillValue/missing_value foi encontrada nessas amostras; não houve preenchimento nem aplicação de máscaras de qualidade. Isso não comprova qualidade regional ou continuidade histórica.

O manifesto registra produto, versão, coleção, DOI, variáveis, unidades, dimensões, resolução, região/CRS, pedido, cobertura do grânulo, tempos lidos, endpoint/parâmetros, job, tamanho/hash e coleta UTC/America/Sao_Paulo. Os horários de coleta não são os tempos das observações. Queries assinadas e tokens não são persistidos.

Os três produtos mensais têm um timestamp representativo por arquivo; sua cobertura catalogada é dezembro/2015. O recorte temporal seleciona grânulos que intersectam a consulta e preserva seus registros nativos completos. Por isso o pedido MUR de 01/12 também inclui o registro de 02/12 às 09h. Os períodos pedido e retornado permanecem distintos.

## Reexecução e problemas resolvidos

As três execuções NASA foram repetidas com todos os sete arquivos reutilizados, sem novas transferências científicas ou novos jobs; hashes e conjunto de jobs permaneceram iguais. A execução de inventário sem rede confirmou todos os nove arquivos e ausência de temporários incompletos.

Falhas iniciais resolvidas: aceite EULA GES DISC pelo titular; parâmetros de variável repetidos no Harmony; comparação exata da relação ESIP `data#`; autenticação nos links de resultado do próprio Harmony. HTML de login foi rejeitado e nunca promovido a dado científico. Detalhes e commits estão no [diário](diario_execucao.md).

## Limites e próximos passos

A caixa terrestre `brasilia_smoke` serve somente a testes de transferência. Não é bacia nem região científica definitiva; nenhuma estação ANA/INMET foi auditada. MERRA-2 e MUR usam Niño 3.4. Polígonos configuráveis são extraídos pelo envelope, sem máscara.

Amostras pequenas não bastam para análise de tendência ou comparação de episódios. A automação está preparada para novos períodos, com limite explícito de grânulos, mas a extração histórica depende de uma região de estudo fundamentada. Nenhuma limpeza, conversão de unidades, EDA ou estatística foi aplicada. O próximo passo deve ser discutido em conjunto.

Para conferir os arquivos locais sem rede:

```bash
.venv/bin/python scripts/fetch_mvp_data.py --inventory-only
```
