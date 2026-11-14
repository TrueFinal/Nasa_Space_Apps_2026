# Inventário da coleta — 2026-11-14

Estado: NOAA obtida e verificada; conteúdo NASA pendente de autenticação. Este
relatório descreve os arquivos disponíveis e não contém EDA ou interpretação ENSO.
Evidências completas: [`inventario_coleta.json`](inventario_coleta.json).

| Dataset/arquivo | Arquivos obtidos | Bytes | Período/registro | Integridade e limites |
|---|---:|---:|---|---|
| NOAA RONI, ASCII original | 1 | 14.752 | 921 trimestres sobrepostos; janeiro/1950–setembro/2026, mês central | SHA-256 validado, registros em ordem e sem duplicatas; zero ausências reconhecidas |
| NOAA, classificação HTML oficial | 1 | 98.060 | Tabela histórica original preservada | SHA-256 validado; conteúdo mantido, sem inferir ou extrair fases locais |
| IMERG Final diário V07 | 0 | 0 | Metadados consultados; último grânulo até setembro/2025 | Conteúdo, unidades, dimensões e ausências ainda não verificados |
| IMERG Final mensal V07 | 0 | 0 | Metadados consultados; último grânulo até setembro/2025 | Conteúdo, unidades, dimensões e ausências ainda não verificados |
| GLDAS Noah mensal 2.1 | 0 | 0 | Metadados consultados; último grânulo até julho/2026 | Conteúdo e qualidade de estimativas modeladas ainda não verificados |
| MERRA-2 mensal 5.12.4 | 0 | 0 | Metadados consultados; último grânulo até setembro/2026 | Conteúdo e qualidade da reanálise ainda não verificados |
| MUR SST 4.1, opcional | 0 | 0 | Metadados consultados; último grânulo até 13/11/2026 | Somente dry-run; conteúdo ainda não verificado |

Total obtido: **2 arquivos, 112.812 bytes**. Hashes e unidades RONI (°C conforme a
definição NOAA) estão no manifesto. RONI é índice regional, sem dimensões de grade;
o HTML é evidência da classificação oficial, sem contagem de registros extraída.
A coleção de arquivos não apresenta problema de integridade identificado.

Os dados ficam em `data/raw/noaa_roni/RONI/global_index/`. Cada arquivo recebeu
SHA-256 e horários UTC/America/Sao_Paulo. Os arquivos originais não foram alterados,
e a segunda execução reutilizou ambos após conferir os hashes. A data de coleta
não é a data das observações. RONI e classificação histórica podem ser revisados
pela fonte; `--refresh` preserva novas revisões por conteúdo.

A última execução de coleta completa registrou quatro falhas explícitas por
`EARTHDATA_TOKEN` ausente, com código de saída 1. Não foi submetido nenhum job
NASA. O modo público confirmou nomes/versões/variáveis, capacidade de recorte e
grânulos disponíveis; isso não comprova continuidade nem download autenticado.

Região terrestre padrão: `brasilia_smoke`, caixa técnica provisória. A seleção
científica de bacia/região brasileira e a auditoria de estações ANA/INMET seguem
pendentes. Os recortes poligonais atualmente usam o envelope, sem máscara, e os
registros temporais de cada grânulo são preservados completos.

Para reproduzir, consultar o [README](../README.md). Para verificar os arquivos
locais sem rede:

```bash
.venv/bin/python scripts/fetch_mvp_data.py --inventory-only
```

Próximo passo de coleta: configurar o token localmente e executar as amostras
NASA documentadas no README. EDA, limpeza e estatística permanecem fora desta entrega.
