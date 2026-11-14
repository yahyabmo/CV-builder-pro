"""La lecture des pages d'un CV PDF importé, sans IA : ce qui range son contenu et ce qui
dit son style.

``reading`` lit chaque page (mots stylés, formes, images, liens) ; ``scan`` fait de même pour
un scan, d'après Tesseract et l'image ; ``structure`` y trouve les colonnes, les titres et les
rubriques ; ``fields`` retrouve chaque champ sur la page ; ``fill`` corrige ce que l'IA a mal
rangé ; ``fonts`` associe une police de l'appli à chaque police du PDF.
"""
