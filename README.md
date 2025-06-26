# Repositório base para o Projeto 3

**Aluno:** Matheus Bulhões – RA 222157

---

## 🧭 Breve descrição dos objetivos

Neste projeto, o objetivo foi portar e acelerar um código computacional na plataforma LiteX. O código escolhido implementa um algoritmo de **regressão polinomial por mínimos quadrados**, utilizado para ajuste de curvas. O foco foi otimizar o trecho mais custoso do ponto de vista computacional, identificado previamente por meio de `profiling` com a ferramenta `gprof`, executada sobre o código rodando na plataforma nativa (PC).

Esse profiling revelou que o maior tempo de execução estava concentrado nas operações repetidas de somatórios envolvendo potências de entradas (`x[k]^n * y[k]`), exigidas na construção das matrizes do sistema linear. Com base nisso, o projeto propôs e desenvolveu uma **aceleração dedicada em hardware** para esse trecho, visando reduzir significativamente o tempo de execução.

Os principais objetivos alcançados foram:

- Portar o código original para a arquitetura simulada com CPU VexRiscv;
- Realizar profiling detalhado do código para identificar gargalos;
- Projetar e implementar um periférico acelerador em Migen;
- Integrar o periférico desenvolvido a fim de substituir o gargalo identificado no software;
- Reduzir o tempo de execução final a partir da aceleração por hardware.

---

## ⚙️ Desafios encontrados

Durante o projeto, vários desafios técnicos foram enfrentados e superados:

### 🕵️‍♂️ Identificação do Gargalo

O profiling realizado revelou que o maior tempo de execução estava concentrado nas operações repetidas de somatórios envolvendo potências de entradas (`x[k]^n * y[k]`), exigidas na construção das matrizes do sistema linear.

📉 **Antes da aceleração:**  
- Tempo de execução completo na plataforma Litex: **~30 s**
- Função `tinyPow` representava >60% do tempo total

Com base nisso, o projeto propôs e desenvolveu uma **aceleração dedicada em hardware** para esse trecho, visando reduzir significativamente o tempo de execução.

### ⚙️ Periférico desenvolvido

Desenvolvemos um módulo Migen chamado `PowerSum`, com as seguintes características:

- Entrada de 32 pares (xk, yk), divididos em dois buffers de 16 posições de modo a implementar **double buffering**, realizando operações em paralelo um dos buffers enquanto o software alimenta o outro com dados
- Execução paralela em 16 unidades `PowerUnit`, que realiza a operação de potência até grau 4 a partir de lógica combinacional
- Multiplicação de `xk^exp` com as entradas `yk` e soma dos 16 valores utilizando árvore binária
- Implementação de um registrador de 64 bits para acúmulo do somatório sem que haja overflow
- Interface via CSR para software enviar dados e coletar o resultado

O hardware desenvolvido foi capaz de realizar a operação ∑ (xk^exp * yk), com k variando de 0 até n, onde n representa o número de pares de entrada utilizados na interpolação polinomial. O valor máximo de n que pode ser processado sem perda de precisão depende diretamente da largura do registrador acumulador utilizado. Nos testes realizados, observou-se que um acumulador de 32 bits apresentava overflow para n em torno de 50, enquanto a versão com acumulador de 64 bits pode, teoricamente, suportar execuções com mais de 1 milhão de entradas sem perigo de overflow.

---

## 🚧 Barreiras alcançadas

Apesar dos avanços, alguns pontos não foram completamente superados:

- O periférico PowerSum não opera diretamente com valores em ponto flutuante. Para lidar com números reais, é necessário utilizar uma abordagem de ponto fixo, por exemplo, multiplicando todos os valores por uma constante (como 1000) antes de enviá-los ao hardware e dividindo o resultado final no software.
- O fluxo de controle do periférico ainda é gerenciado inteiramente pelo software. Embora o design atual funcione corretamente, uma implementação mais avançada — utilizando FIFO, DMA ou algum tipo de controle automático — poderia tornar o uso mais eficiente e reduzir a complexidade do código em C.

---

## ✅ Comentários gerais e conclusões

Ao final, o tempo de execução do código na plataforma LiteX foi reduzido de aproximadamente 30 segundos (para uma entrada com 500 dados) para cerca de 2 segundos, representando uma economia superior a 90% no tempo total. Para uma avaliação mais precisa do ganho de desempenho, o ideal seria realizar um novo profiling após a inclusão do periférico acelerador. No entanto, isso não é viável na plataforma LiteX, já que ferramentas como o gprof não são compatíveis com o ambiente utilizado.

Este projeto foi importante didaticamente para aprender de forma aplicada os conceitos de profiling, paralelismo e aceleração por hardware. A plataforma LiteX demonstrou grande flexibilidade, ainda que exija atenção aos detalhes de integração e síntese. Além disso, o uso do **profiling** ajudou a garantir que o esforço de hardware estivesse concentrado exatamente onde mais impactaria no desempenho final.
