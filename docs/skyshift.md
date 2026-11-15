# Dados públicos e plotagem SkyShift no laboratório

Origem: [Nsa-2026/skyshift](https://github.com/Nsa-2026/skyshift), revisão
`a6427d86ee7e90da700b35eb26d554de6dbbf777`. O recibo [skyshift_execution.json](skyshift_execution.json)
registra revisão, inventário, execução dos scripts e resultados locais. Não é um novo
levantamento nem confirmação dos candidatos do arquivo público.

## Métodos encontrados no código de origem

| Código SkyShift | Método | Integração no laboratório |
|---|---|---|
| `server/src/skyshift_server/stack.py` | Grade TAN comum, norte acima/leste à esquerda; interpolação bilinear ponderada pela máscara. Visitas combinadas por mediana após nivelar o céu. | Os binários públicos já contêm esse processamento. Os nossos FITS continuam nativos; não foram reprojetados para fazer fotometria. |
| `web/src/blink/math.ts` | Limites compartilhados por detector; percentis `0.5+9.5c` e `100−0.05×10^(2.3c)`; `asinh(10t)/asinh(10)`. | Mesma normalização de exibição, com contraste ajustável. |
| `web/src/blink/paint.ts` | Negativo `#EDF0EF → #18202E`, positivo invertido e diferenças vermelho/azul; ausência de dados transparente. | Paleta selecionável nas imagens locais; explorador público em negativo e exportação `comparison_negative.png`. |
| `web/src/blink/index.ts` | Blink, média e diferenças; fundo removido opcionalmente só na exibição. | Explorador com detector fixo, escala comum, média e diferença para o primeiro quadro. Operações entre quadros exigem centros coincidentes. |
| `web/src/blink/marks.ts` | Camadas separadas de detecções, catálogos e posições previstas. | Detecções publicadas por época em círculos; posições conhecidas previstas em losangos; projeção TAN e marcas limitadas à cobertura. |
| `web/src/blink/allwave.ts` | Combina detectores em unidades do próprio ruído, dividido por √N; não é RGB nem fluxo integrado físico. | Método documentado; não usado para acrescentar fluxo às medidas ou preencher os 102 canais. |

As diferenças implementadas são subtrações visuais diretas, com escala simétrica,
sem equalização de PSF ou significância estatística por pixel. Não são a diferença
com limiar de ruído do player original. Média/diferença são bloqueadas em sequências
com centros variáveis. A largura/comprimento de onda pode mudar dentro de um detector;
uma diferença também pode ser espectral. A média do explorador é uma média dos produtos
disponíveis, não uma nova mediana das exposições originais.

Nas imagens locais, o blink automático conserva o detector e exige CWAVE a até
0,01 µm do quadro inicial. Isso limita mudanças de banda, mas não cria uma banda
fixa calibrada nem alinha os WCS nativos. A inspeção manual continua disponível.

## Importar e reproduzir

```powershell
git clone https://github.com/Nsa-2026/skyshift.git ../skyshift_nsa_2026
git -C ../skyshift_nsa_2026 checkout a6427d86ee7e90da700b35eb26d554de6dbbf777
python -m pip install -r requirements-skyshift.txt
python scripts/skyshift_import.py --source ../skyshift_nsa_2026 --report outputs/infrared/report.json --run-scripts --receipt docs/skyshift_execution.json
./start-infrared.ps1
```

O clone já existente pode ser reutilizado. Sem relatório local, omita `--report`:
a importação e as agregações públicas continuam disponíveis. Sem `--run-scripts`,
apenas importe os produtos e associe as amostras. Os scripts originais são executados
explicitamente pela CLI; o servidor HTTP nunca os executa por solicitação de página.

O importador aceita a origem acima, registra o commit e exige código/dados limpos.
JSONs, dimensões dos binários e caminhos são verificados antes de publicar o manifesto.
Cada arquivo recebe SHA-256; o servidor confere o hash antes de fornecê-lo. Os produtos
ficam em `data/skyshift/`, ignorados pelo Git, aproximadamente 129 MB. Não são necessários
Firebase, credenciais Google ou acesso ao bucket privado para explorar esse snapshot.

No Windows, os scripts originais são iniciados com UTF-8 para que a escrita dos
JSONs não dependa da página de códigos do sistema. A execução registrada usou Python
3.13.7; os projetos upstream declaram Python 3.12. A compatibilidade dos caminhos
executados foi verificada pelos testes, sem afirmar suporte a todos os comandos upstream.

## Enriquecimento científico e limites

- **Arquivo público:** 483 JSONs, 871 imagens, 106 conjuntos e 11.192 candidatos.
  Existem 365 produtos de objeto, mas somente 83 têm imagens pré-calculadas.
  Espectros sem imagens permanecem consultáveis; medidas saturadas são excluídas
  do gráfico, fluxos negativos são preservados e só 0,75–5,00 µm é exibido.
- **Associação local:** cada amostra SPHEREx é comparada às posições publicadas
  dos candidatos até 3″, sem propagação. A compatibilidade temporal requer ±1 dia;
  compatibilidade de detector é registrada separadamente. No relatório Slipher,
  268 amostras foram verificadas e não houve associação dentro do raio. Isso não
  prova ausência de fontes: a lista pública é seletiva, tem outras regiões/épocas
  e não é um catálogo completo. Nenhuma posição de outro alvo foi forçada sobre
  as imagens Slipher.
- **Fotometria independente:** executamos a função real `scripts/science/phot.py:measure`
  sobre os FITS nativos locais, com `SCIENCE`, `FLAGS`, `VARIANCE` e os mapas
  CWAVE/CBAND. O adaptador interpola esses mapas na posição recentrada. Usa abertura
  de 2 e 3 px, anel 4–9 px, recentragem até 1,5 px, rejeição de máscaras/saturação e
  correção upstream 1,033 em 2 px. Não usa a nossa máscara Gaia e não é uma previsão
  orbital ou validação de identidade. Aceitou 12/12 exposições. Os hashes dos FITS
  são conferidos antes da execução; a comparação fica em uma coluna própria e não
  substitui a medida primária sem correção de PSF. As medidas primárias e os FITS
  permaneceram inalterados.
- **Validações:** `scripts/validate/build_validation.py` foi executado sobre os
  produtos publicados e as entradas disponíveis em `scripts/validate/data`.
  Reagregou V1, V2, V3, V4, V6, V7, V8 e V11 como `pass`; V5, V9 e V10 ficaram
  `pending` porque os relatórios das zonas não estão disponíveis. Não se repetiu
  a detecção bruta que produziu as entradas publicadas, nem o teste remoto de latência.
- **Objetos distantes:** `scripts/validate/distant.py` foi executado com as entradas
  publicadas. O resultado continua compatível com acaso; não confirma um planeta.
- **Não recalculados:** recuperação bruta V1/V4/V6/V7, espectros de zonas V8,
  injeção de planetas, pré-cálculo remoto e ajustes completos NEATM/Haser dependem
  de novos recortes, tabelas Parquet, geometria Horizons ou serviços externos.
  O relatório lista essas dependências, sem apresentar resultados herdados como
  novas medições locais. O fluxo de ingestão MPC/Gaia/WISE existente continua disponível.

Produtos: `report.json` recebe `skyshift_context` e, quando a impressão do manifesto
coincide, `skyshift_photometry`. As versões exportáveis são `skyshift_context.json`
e `skyshift_photometry.json`. Resultados de outra revisão SkyShift ou de outro
manifesto local não são anexados como se pertencessem à análise atual.

APIs locais: `GET /api/skyshift`, `GET /api/skyshift/object?slug=barnard&frames=frames_months_5.json`
e `/skyshift-data/<arquivo.bin>` (apenas arquivos do manifesto). O explorador funciona
mesmo quando ainda não existe um relatório local. Todos os dados são tratados como
texto ou números; nomes externos não são inseridos como HTML.

## Atribuição e verificações

Paleta, convenções de formato e métodos de normalização adaptados do SkyShift,
Apache-2.0; [licença original](skyshift-LICENSE.txt). Os scripts e dados importados
permanecem vinculados à revisão de origem. Imagens: NASA/JPL-Caltech/SPHEREx/IPAC–IRSA;
astrometria de referência: ESA/Gaia/DPAC; previsões conhecidas conforme proveniência MPC/MOST.

```powershell
python -m pytest -q
node --test web/infrared-mask/app.test.mjs web/infrared-mask/plate.test.mjs web/infrared-mask/skyshift.test.mjs
npm.cmd run check --prefix web/site
```
