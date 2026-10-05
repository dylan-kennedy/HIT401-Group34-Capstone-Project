# HIT401-Group34-Capstone-Project

A project repository for Group 34's 'HIT401 - Capstone Project' code.

Supervisor: Dr Cat Kutay

Group 34 Team:

Krishna Dhakal	S396451
Gaurab Gaihre	S387897
Dylan Kennedy	S343881
Sachin Kharel	S399310

Datasets origins\*:
"GroundwaterHeads\_20250718" - Shared by supervisor Dr Cat Kutay via email with the team.

"Bores.csv" inside "NT-NaturalResourceMapsBoreData" - Can be downloaded directly through Northern Territory's Natural Resource Maps website (at https://nrmaps.nt.gov.au/nrmaps.html), but the current version 4/09/26 was provided via email exchange between Group 34, supervisor Dr Cat Kutay, and Associate Professor Dylan Irvine, by Dylan.

"BOM-Datasets" - Provided by supervisor, but can and likely will be updated by location from the source at the BOM website: https://www.bom.gov.au/climate/data/

\*This information is also located alongside the datasets under "DataSources.txt" - possibly remove both this + the .txt file later.

# Edit readme later

To Use python Files:

Will need to run python install commands for packages listed before code next to 'import X' (all simple) if you don't have them installed already:
folium, pandas, matplotlib, requests, probably one or two more but can't remember which are main packages and which come with those main packages, just run the install command for the name of the package and see what it says I guess.

can use 'pip install (package name)' if you have 'pip' configured / installed, otherwise need to configure / install pip first







Running Krishna's Code (edit as we go, file path will likely change later)



Unzip 'data.zip' from krishna-code/

* file size too big for GitHub repo...



> Set up virtual environment 



"python -m venv krishna-code/.venv"



> Activate virtual environment



"krishna-code/.venv/Scripts/activate.ps1"



> Install dependencies (from requirements.txt)



"pip install -r krishna-code/requirements.txt"



> Run the app.py file (modify to latest version num) with streamlit



"streamlit run krishna-code\\"app(v1.2).py"" - include quotes around "app(v1.2).py", until we rename it.

