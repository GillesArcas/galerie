# Description

journal est un utilitaire en ligne de commande permettant de créer des galeries d'images et de vidéos. Les images et vidéos peuvent être organiser par répertoires, par dates ou les deux. De plus, les galeries créées peuvent inclure le contenu d'un fichier journal. Un fichier journal est un fichier texte, respectant une syntaxe très simple (le format Markdown), organisé par dates et incluant du texte et des images.

- [Installation](#installation)
- [Utilisation](#utilisation)
- [Description d'une galerie](#description-dune-galerie)
- [Création d'une galerie](#création-dune-galerie)
- [Autres commandes](#autres-commandes)
- [Règles d'écriture d'un fichier journal](#règles-décriture-dun-fichier-journal)
- [Fichier de configuration](#fichier-de-configuration)

# Installation 

A compléter

# Utilisation 

La principale utilisation de journal est la création de galeries à partir de répertoires de médias. Ceci se fait en ligne de commande, par exemple avec la commande suivante :

`$ journal --gallery /foo/mygallery --imgsource /bar/mypictures`

Cette commande crée dans le répertoire /foo/gallery un fichier index.htm qu'il faut ouvrir pour visionner la galerie. Toutes les options de création sont décrites dans la suite. 

Toutes les options peuvent être abrégées si elles ne créent pas d'ambiguïté. Ainsi,

`$ journal --gallery /foo/mygallery --imgsource /bar/mypictures --recursive` 

est équivalent à

`$ journal --gal /foo/mygallery --img /bar/mypictures --rec` 

# Description d'une galerie

A compléter

# Création d'une galerie

## Présentation

Une galerie est créée (ou mise à jour) avec la commande `--gallery`. Cette commande, suivie du nom du répertoire racine de la galerie, nécessite de donner le nom du répertoire source des médias avec l'option `--imgsource`. 

`$ journal --gallery /foo/bar/mygallery --imgsource /spam/egg/mypictures` 

Il y a trois façons d'organiser une galerie à partir des médias contenus dans un répertoire :

* on peut conserver la structure de sous-répertoire, en créant une page par sous-répertoire, avec l'option `--bydir`,
* on peut regrouper les médias par dates, en créant une section par date ayant la date pour titre, avec l'option `--bydate`,
* on peut utiliser un ficher journal avec l'option `--diary`. Un fichier journal est un fichier de syntaxe simple, organisé par date et associant à chaque date un texte et des images. Une page peut être créée avec seulement ces données ou complétée avec les médias d'un répertoire source.

Les options `--bydir` et `--bydates` peuvent être combinées. Deux options supplémentaires permettent de préciser les données utilisées avec les options `--bydir`, `--bydates`  et `--diary`:

* l'option `--dates` qui limite les médias utilisés dans une galerie à une sélection de dates,
* l'option `--recursive` qui indique si il faut considérer les sous-répertoires du répertoires source.

Finalement, une fois la configuration d'une galerie établie, il suffit d'utiliser l'option `--update` pour mettre à jour une galerie avec les options qui ont permis de la créer.

## Quelques exemples

Créer une galerie organisée par sous-répertoires :

`$ journal --gallery /foo/mygallery --imgsource /bar/mypictures --bydir true` 

Créer une galerie organisée par date, en limitant les dates à une plage et en incluant les sous-répertoires :

`$ journal --gallery /foo/mygallery --imgsource /bar/mypictures --bydates true --dates 20200701-20200731 --recursive` 

Créer une galerie organisée par dates et sous-répertoires :

`$ journal --gallery /foo/mygallery --imgsource /bar/mypictures --bydates true --bydir true`

Mise à jour d'une galerie en utilisant les options qui ont permis de la créer :

`$ journal --gallery /foo/mygallery --update`

## Description complète des options de création de galeries

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

`--recursive true/false` (défaut `false`)

A compléter

`--dest` 

??

`--forcethumb`

bla bla

# Autres commandes

L'utilitaire propose également les commandes suivantes :

`--create <chemin de répertoire> --imgsource <chemin de répertoire> --dates <spec_date> --recursive true|false`

crée un fichier journal en considérant les médias spécifiés par les options --imgsource --dates --recursive avec un comportement identique à celui rencontré pour la commande --gallery. Le fichier journal est initialisé avec un texte réduit aux dates des médias considérés.

`--blogger <chemin de répertoire> --url <url> [--check] [--full]`

exporte le journal contenu dans le répertoire au format Blogger. L'url doit pointer sur un page affichant les mêmes images que le fichier journal. Ceci est imposé par le fait qu'il n'est pas possible d'uploader des images sur blogger par programme. La page Blogger est générée dans le presse-papier. L'option `--check` force une comparaison des images locales et sur Blogger si des images de même nom ont pu changer de contenu. L'option `--full` copie dans le presse-papier une page Web complète ce qui permet de la sauver et de la tester localement.

`--resetcfg`

remet le fichier de configuration dans sa configuration par défaut.

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

# Fichier de configuration

Un fichier de configuration permet de configurer certaines propriétés d'affichage. Ce fichier se nomme `.config.ini` et se situe dans le répertoire racine de la galerie. Ce fichier est organisé en trois sections :

- la section `source` qui reprend les options de création données en ligne de commande. Cette section contient les valeurs utilisées quand on utilise l'option `--update`.
- la section `thumbnails` qui permet de spécifier quelques paramètres d'affichage (affichage des méta-données, affichage des noms de répertoire, instant de capture des vignettes pour les vidéos),
- la section `photobox` qui reprend les paramètres du module tiers photobox qui affiche les médias unitairement.

Le fichier de configuration est auto-documenté et donne pour chaque paramètre une brève description ainsi que les valeurs qu'il peut prendre.

# Mesures de précaution

Rien de dommageable mais ça peut être utile d'avoir les remarques suivantes en tête.

- La création d'une galerie met à jour le répertoire des vignettes de façon à ce que ce répertoire contiennent exactement les vignettes des médias considérés dans la galerie. En conséquence, si un média est supprimé, la vignette correspondante est également supprimée. Ce fonctionnement est souhaitable mais si on met à jour une galerie en oubliant un paramètre, par exemple on oublie --recurse qui va traiter tous les sous-répertoires, il peut arriver qu'un grand nombre de vignettes soient supprimées. Pas irrémédiable mais il peut falloir un peu de temps pour tout recréer.
- --update ne mémorise pas le nom de galerie
- une seule config par répertoire
- Les valeurs des paramètres de configuration de la section [source] ne sont utilisés qu'avec la commande --update. Ils ne viennent pas en défaut d'un paramètre absent si --update n'est pas utilisé.

