# conda env export | grep -v "^prefix: " > environment.yml
# pip list --format=freeze > requirements.txt
git add *.py *.txt *.sh */*.py */*.yaml *.md */*/*.ino */*.json */*.ipynb *.yml
git commit -m "eod"
git push -u origin main