# Identificação de objetos no protótipo SPHEREx

Investigação em 15/11/2026. Este documento avalia métodos; não representa um classificador implementado ou uma descoberta. A paleta colorida do visualizador representa intensidade e não fornece classe física.

## Resultado da investigação

| Objeto | Associação com objeto conhecido | Busca de candidatos novos | Dados necessários |
|---|---|---|---|
| Estrelas | Viável com Gaia/SIMBAD, propagando posições até a observação | Detectar fontes e comparar posição, forma e variação de brilho | Astrometria, incertezas, PSF e fotometria por exposição |
| Anãs marrons | Viável quando há identificação catalogada; ausência no Gaia não exclui uma anã marrom | Combinar cores/espectro infravermelho e movimento próprio; comparar com modelos e padrões | Fluxos calibrados em várias bandas, curvas de resposta, épocas e catálogos WISE/2MASS/SIMBAD |
| Asteroides | Viável por posição prevista na data e no ponto de vista do SPHEREx | Associar detecções próximas no tempo em trajetórias; confrontar órbitas conhecidas | Horário individual, posição do observador, coordenadas e incertezas das fontes |
| Cometas | Viável por efemérides e catálogo orbital | Movimento mais emissão extensa/possível coma e informação espectral | Efemérides, PSF, imagem de superfície e espectrofotometria; morfologia sozinha é ambígua |

“Associação” significa uma contraparte provável em dados existentes. “Candidato” significa um sinal a revisar. A confirmação exige evidência adicional; não se transforma uma cor do mapa em rótulo físico.

## Verificação empírica em catálogo

Uma consulta TAP real ao espelho oficial SIMBAD/Harvard retornou:

| Identificador consultado | Identificador principal retornado | Tipo catalogado | Tipo espectral |
|---|---|---|---|
| Epsilon Indi B | `* eps Ind B` | `BD*` (anã marrom) | T1V+T6V |
| WISE J085510.83-071442.5 | `WISEA J085510.74-071442.5` | `BD*` (anã marrom) | Y2 |

A consulta exata e a resposta estão em [simbad_brown_dwarf_check.json](simbad_brown_dwarf_check.json). Isso demonstra a viabilidade de recuperar classes conhecidas por catálogo, não a capacidade de classificar os pixels do SPHEREx. A posição retornada de WISE 0855 difere da coordenada antiga do desafio; conferir a época astrométrica é necessário para associar pixels a objetos de grande movimento próprio.

Fonte: [SIMBAD Harvard TAP](https://simbad.cfa.harvard.edu/simbad/sim-tap/).

## Caminho mais útil para o hackathon

1. **Começar por objetos conhecidos:** consultar SIMBAD e Gaia por região, trazer nome/tipo catalogado, distância angular e origem da classificação. Propagar movimentos próprios e incluir incertezas, paralaxe e mistura de fontes quando relevantes. Proximidade no céu sozinha não garante que o mesmo objeto produziu o pico SPHEREx.
2. **Identificar asteroides/cometas conhecidos:** usar as exposições individuais com horários, não o horário médio de um mosaico semestral. Consultar efemérides com geometria do SPHEREx e comparar as posições previstas com fontes detectadas. Guardar a diferença angular e a incerteza, sem rótulos automáticos de descoberta.
3. **Depois buscar candidatos:** detectar fontes nas imagens nativas, eliminar defeitos/contaminação e associar observações próximas. Usar cores e espectros para candidatos a anãs marrons; movimento e órbitas para corpos do Sistema Solar. O XGBoost existente separa fontes observadas de contaminação instrumental: não foi treinado para as quatro classes físicas.
4. **Validar com identidades reservadas:** separar objetos entre treino e teste, medir completude e contaminação por classe e registrar a origem dos rótulos. Uma detecção na posição esperada de um alvo de demonstração não é uma avaliação independente.

Esses passos são uma proposta de implementação decorrente da investigação, não resultados de um treino realizado nesta atualização.

## Serviços disponíveis e limites verificados

### SIMBAD e Gaia: tipos catalogados

SIMBAD oferece classificação, identificadores e referências bibliográficas por objeto, consultáveis via TAP. Há distinção entre objeto classificado e candidato. Gaia fornece medidas astrométricas úteis para contrapartes estelares, mas o catálogo não inclui toda fonte infravermelha: a ausência de contraparte não é evidência suficiente de artefato nem de anã marrom. A sobreposição Gaia atual é contexto astrométrico e usa movimento linear aproximado.

Fontes: [SIMBAD](https://simbad.cds.unistra.fr/simbad/), [Gaia DR3](https://gea.esac.esa.int/archive/documentation/GDR3/).

### Asteroides e cometas: MOST e JPL

O MOST da IRSA localiza imagens que interceptam a trajetória de um objeto conhecido. O tutorial oficial inclui SPHEREx. Ele é útil para perguntar “em quais imagens este objeto aparece”; não é um classificador de fontes desconhecidas numa imagem. Para a pergunta inversa — quais objetos conhecidos podem estar no campo numa data — o JPL Small-Body Identification API é uma opção.

O JPL aceita posição/velocidade de observador espacial. O parâmetro `xobs` exige coordenadas cartesianas **ICRF**, posição em km e velocidade opcional em km/s. Os FITS locais contêm `X_SC`, `Y_SC`, `Z_SC`, velocidades e origem `GEOCENTER`; essa origem, isoladamente, não confirma a orientação ICRF. A convenção precisa ser verificada/convertida antes de executar associações científicas. Usar um observatório terrestre como substituto pode deslocar objetos próximos por paralaxe. Magnitude visual prevista não equivale ao fluxo infravermelho SPHEREx.

Fontes: [tutorial MOST/SPHEREx](https://caltech-ipac.github.io/irsa-tutorials/most-queries/), [JPL SB Identification](https://ssd-api.jpl.nasa.gov/doc/sb_ident.html).

### Anãs marrons: espectros, não a paleta de cor

A biblioteca SpeX e o SPLAT oferecem espectros e ferramentas de classificação de anãs frias. Para aplicá-los ao SPHEREx, os padrões devem ser comparados após integração nas respostas espectrais relevantes e com incertezas/contaminação tratadas. A cobertura SpeX típica não equivale automaticamente às 102 bandas SPHEREx. Movimento próprio e cores WISE ajudam na seleção, mas objetos de tipos diferentes podem compartilhar cores aparentes.

O espectro atual do visualizador é exploratório, em abertura, com épocas misturadas e comprimentos de onda do centro do campo. Para classificação física, usar espectrofotometria calibrada, tratar mistura de fontes e controlar variabilidade entre épocas. O serviço oficial pode demorar minutos ou horas, por isso deve ser uma tarefa separada com acompanhamento de progresso.

Fontes: [SPLAT](https://splat.physics.ucsd.edu/splat/api.html), [IRSA Spectrophotometry](https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html).

## Todas as imagens

A interface agora oferece a listagem completa dos resultados das coleções DR1/QR3, incluindo campos profundos, com filtros e páginas de 50 linhas. A paginação só organiza a tabela; não remove arquivos. O padrão de carregamento do detector é “Todas as exposições”. É possível abrir qualquer item individualmente e exportar o catálogo inteiro.

A animação evita contar duas vezes uma exposição física presente em coleções diferentes, preferindo DR1. As versões alternativas continuam na tabela e podem ser abertas. Resultados de consultas que falharam não são apresentados como uma lista completa; downloads que falharam permanecem acessíveis para nova tentativa.

A IRSA documenta `MAXREC` sem limite por padrão. A aplicação não define um teto de linhas na consulta; `MAXREC=0` seria apenas metadados, e por isso não é usado. Disponibilidade do serviço, tamanho do campo e memória do navegador ainda afetam a execução. Para regiões muito grandes, usar “Só listar; abrir uma por vez”.

Fonte: [IRSA SIA v2](https://irsa.ipac.caltech.edu/ibe/sia.html).
