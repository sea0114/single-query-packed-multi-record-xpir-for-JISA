# Flat source package

`jisa-source-20260926.zip` contains main.tex, supplement.tex, their same-level inputs, references.bib and the data-generated primary figure. It is derived from `paper/` using the hash mapping in `flattening-map.json`. It uses installed TeX Live packages rather than copying publisher/system packages.

Extract into a new directory and run `latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex supplement.tex`. Flattening addresses Editorial Manager's source-directory restriction; JISA-specific formatting, anonymization and author declarations remain to be confirmed. It does not certify readiness for submission.
