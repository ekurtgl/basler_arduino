# conda env export | grep -v "^prefix: " > environment.yml
# conda export -n <env_name> | grep -v "^prefix: " > environment.yml
# pip list --format=freeze > requirements.txt
git add *.py *.txt *.sh */*.py */*.yaml *.md */*/*.ino */*.json */*.ipynb *.yml */*.png */*.jpg .vscode/*.json
git commit -m "eod"
git push -u origin main