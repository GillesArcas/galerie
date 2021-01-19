# Description

journal est un utilitaire permettant de créer des galeries d'images et de vidéos. Les images et vidéos peuvent être organiser par répertoires, par dates ou les deux. De plus, les galeries créées peuvent inclure le contenu d'un fichier journal. Un fichier journal est un fichier texte, respectant une syntaxe très simple (le format Markdown), organisé par dates et incluant du texte et des images.

# Création d'une galerie

## Présentation

Une galerie est créée (ou mise à jour) avec la commande `--gallery`. Cette commande, suivie du nom du répertoire racine de la galerie, nécessite de donner le nom du répertoire source des médias avec l'option `--imgsource`. 

`$ journal --gallery /foo/bar/mygallery --imgsource /spam/egg/mypictures` 

Il y a trois façons d'organiser une galerie à partir des médias contenus dans un répertoire :

* on peut conserver la structure de sous-répertoire, en créant une page par sous-répertoire, avec l'option `--bydir`,
* on peut regrouper les médias par dates, en créant une section par date ayant la date pour titre, avec l'option `--bydate`,
* on peut utiliser un ficher journal avec l'option `--diary`. Un fichier journal est un fichier de syntaxe simple, organisé par date et associant à chaque date un texte et des images. Une page peut être créée avec seulement ces données ou complétée avec les médias d'un répertoire source.

Deux options supplémentaires permettent de préciser les données utilisées avec ces options :

* l'option `--dates` qui limite les médias utilisés dans une galerie à une sélection de dates,
* l'option `--recursive` qui indique si il faut considérer les sous-répertoires du répertoires source.

Finalement, une fois la configuration d'une galerie établie, il suffit d'utiliser l'option `--update` pour mettre à jour une galerie avec les options qui ont permis de la créer.

## Quelques exemples

Créer une galerie organisée par sous-répertoires :

`$ journal --gallery /foo/mygallery --imgsource /bar/mypictures --bydir true` 

Créer une galerie organisée par date, en limitant les dates à une plage et en considérant les sous-répertoires :

`$ journal --gallery /foo/mygallery --imgsource /bar/mypictures --bydates true --dates 20200701-20200731 --recursive` 

Créer une galerie organisée par dates et sous-répertoires :

`$ journal --gallery /foo/mygallery --imgsource /bar/mypictures --bydates true --bydir true`

Mise à jour d'une galerie en utilisant les options qui ont permis de la créer :

`$ journal --gallery /foo/mygallery --update`

## Description complète des options

L'option `--gallery` permet de créer et mettre à jour une galerie. La galerie est définie par les options `--imgsource`, `--bydir`, `--bydates`, `--diary`, `--dates` et `--recursive`. L'option `--update` permet de remplacer les cinq options précédentes. 

`--gallery <chemin de répertoire>`

spécifie le répertoire racine de la galerie. Dans ce répertoire se trouvent l'ensemble des fichiers créés. Le point d'entrée est le fichier `index.htm`.

`--imgsource <chemin de répertoire>`

spécifie le répertoire où se trouve les médias à inclure dans la galerie.

`--bydir true/false` (défaut `false`)

détermine si la galerie est organisée par répertoire et sous-répertoire, une page par répertoire. Peut-être combiné avec `--bydates`.

`--bydates true/false` (défaut `false`)

détermine si la galerie est organisée par dates. Peut-être combiné avec `--bydir`.

`--diary true/false` (défaut `false`)

détermine si la galerie est organisée à partir d'un fichier journal. 

`--dates diary/source/yyyymmdd-yyyymmdd` (défaut `source`)

spécifie les dates à considérer pour ajouter des images d'un répertoire source à un fichier journal. Si l'argument vaut `diary`, on n'ajoute que des images correspondant aux dates du fichier journal. Si l'argument vaut `source`, on ajoute toutes les images du répertoire source. Sinon, on n'ajoute que les images dans la plage de dates `yyyymmdd-yyyymmdd`.

# Règles d'écriture d'un fichier journal

Un fichier journal est un fichier texte respectant le format Markdown avec les quelques contraintes listées ci-dessous. Ces contraintes permettent de structurer le journal. 

### Structure d'enregistrement

Un fichier journal est constitué d'enregistrements. Un enregistrement est constitué dans cet ordre de :

* un champ date obligatoire,
* un champ texte,
* un champ médias,
* un séparateur d'enregistrement.

### Le champ date

Le champ date doit apparaitre seul en première ligne de l'enregistrement avec le format suivant :

[2020/11/06]

Si la date est absente, la lecture du fichier journal déclenche une erreur. Une erreur est également déclenchée si les dates ne sont pas en ordre croissant. Des enregistrements différents peuvent avoir la même date.

Le champ date est ignoré par les fonctions d'exportation. Il est par contre nécessaire pour associer les médias d'un répertoire à chaque enregistrement.

### Le champ texte

Le champ texte doit respecter la syntaxe Markdown sans autre contrainte.

### Le champ médias

Deux types de média sont pris en compte : les images et les vidéos. Les images (au format JPEG) sont spécifiées avec le format ![]\(\) standard. Les vidéos (au format MP4) sont spécifiées avec la syntaxe des liens []\(\). Les crochets doivent restés vide (pas de texte alt ou de texte de lien).

![](une_image.jpg)
[](une_video.mp4)

Ces spécifications sont regroupées en fin d'enregistrement, un média par ligne en début de ligne. Si la ligne qui suit un média  n'est pas un média, elle est considérée comme une légende (texte lié au média apparaissant en dessous) par les fonctions d'exportation.

Un éventuel texte après les médias est ignoré.

### Séparateur d'enregistrements

Un séparateur d'enregistrement est une barre de séparation de longueur 6 au moins.