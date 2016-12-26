#!/bin/sh
pdflatex "\def\formula{E=\frac{m_1v^2}{2}}\input{formula.tex}"
convert -density 300 formula.pdf -quality 90 formula.png
