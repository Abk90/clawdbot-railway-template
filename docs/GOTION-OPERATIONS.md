# OpenClaw Gotion — mode opératoire chantier

## Ce qui est automatisé

Le coordinateur Telegram du groupe `Projet Gotion — Pilotage International — Coordination` :

- lit les messages des acteurs autorisés, même sans mention du bot ;
- transcrit les vocaux français/darija et analyse jusqu'à quatre photos par message ;
- ouvre un dossier `GOT-...` pour un achat, une réception, une consommation/pose, un nouvel ouvrier, un rapport journalier ou un incident ;
- conserve les faits, preuves, inconnues et questions dans une base SQLite persistante ;
- pose au maximum trois questions bloquantes à la fois, dans la langue de l'acteur ;
- recherche en lecture seule les références exactes Odoo ;
- prépare une proposition immuable `GOA-...` ;
- relance les rapports quotidiens manquants du lundi au samedi ;
- crée, après deux commandes explicites d'Ahmed, une note, une tâche, une demande de prix achat ou un transfert interne **en brouillon**, puis relit le résultat Odoo.

Le bot ne confirme jamais une commande, ne valide jamais une réception ou un transfert, ne crée pas de facture ou paiement, et ne publie pas de données RH privées.

## Authentification OpenAI par la souscription

Le moteur conversationnel Gotion doit utiliser l’authentification Codex liée à la souscription ChatGPT, pas le solde séparé d’une clé API OpenAI.

Depuis la conversation **privée** avec `@Openclaw_belkora_bot` :

```text
/login codex
```

Ouvrir ensuite le lien OpenAI fourni, saisir le code d’appareil et valider avec le compte abonné. Ne jamais copier ce code dans le groupe. Après confirmation, envoyer `/new` dans le groupe Gotion pour ouvrir une session propre, puis faire un test sans écriture Odoo.

Si le bot indique que l’authentification est expirée, refaire uniquement cette procédure privée. La clé `OPENAI_API_KEY` et la souscription ChatGPT ont des facturations distinctes ; une clé API sans crédit ne doit pas être confondue avec l’accès Codex de la souscription.

## 1. Ajouter un chef de chantier

L'acteur doit d'abord être présent dans le groupe. Ahmed relève et vérifie son identifiant Telegram numérique exact, puis envoie lui-même :

```text
/gotion_actor add <TELEGRAM_ID> chef_chantier darija daily voice Mustapha
```

Variantes :

- langue : `fr`, `darija` ou `ar` ;
- rapport : `daily` ou `nodaily` ;
- réponse : `voice` ou `text` ;
- rôles autorisés : `chef_chantier`, `field_worker`, `project_manager`, `co_manager`, `stock_manager`, `finance`, `hr`.

Retrait d'accès :

```text
/gotion_actor remove <TELEGRAM_ID>
```

Ne jamais choisir un homonyme ou ajouter une personne à partir de son seul prénom.

## 2. Rapports attendus du terrain

### Achat chantier

Le chef peut envoyer un vocal en darija et les photos du ticket/bon. Il doit préciser :

- date et personne ayant acheté ;
- fournisseur tel qu'affiché ;
- société concernée ;
- article, quantité, unité, prix unitaire et total ;
- caisse ou moyen de paiement ;
- lieu de réception physique ;
- preuve de réception distincte du ticket.

Exemple darija :

```text
شريت اليوم جوج raccords من Droguerie X لحساب Miya. خلصت من caisse Mustapha.
كل واحد بـ 50 DH. تسلماتهم فـ chantier Gotion، وهادي تصويرة البون وتصويرة السلعة.
```

### Consommation ou pose

La pose est distincte de l'entrée en stock. Il faut :

- date, poseur et zone exacte ;
- produit ou code Odoo exact ;
- quantité et unité ;
- société, emplacement source et destination ;
- lot/colis si le produit est suivi ;
- photos de pose et description de ce qui est visible.

Exemple darija :

```text
اليوم ركبت 6 raccords AIxxx فـ zone Sud، خرجتهم من stock chantier Gotion.
هادو تصاور قبل ومن بعد. باقي فالستوك 4، خاص Youssef يأكد الكمية واللوكاسيون.
```

Le bot ne convertit jamais des plateaux en m² et ne mélange pas le stock chantier, la consommation Belkora et `Consommé par VIAOM`.

### Nouvel ouvrier

Dans le groupe, on ne partage jamais le numéro CIN, la date de naissance, le téléphone, l'adresse, le taux détaillé ou les documents RH. Le chef annonce seulement : nom, date d'entrée, chantier/équipe, statut et disponibilité des documents en privé.

La proposition Odoo devient une tâche contrôlée couvrant : vérification privée, régime CNSS, taux confirmé, fiches PB/MB, badge, validation visuelle Ahmed, impression/test Youssef et premier pointage.

## 3. Proposition et validation Odoo

Quand le dossier est complet, le bot publie :

- l'identifiant `GOT-...` ;
- le résumé et les preuves ;
- les identifiants Odoo résolus ;
- l'action et son impact ;
- l'identifiant de proposition `GOA-...` ;
- la mention explicite qu'aucune écriture n'a encore eu lieu.

Ahmed vérifie puis envoie deux messages séparés :

```text
/gotion_approve GOA-YYYYMMDD-XXXXXX
/gotion_execute GOA-YYYYMMDD-XXXXXX
```

L'approbation expire après quatre heures. L'exécution contrôle encore les références, la société, les emplacements, le type d'opération et les doublons. Elle lit ensuite le nouvel enregistrement et renvoie le lien Odoo.

Les actions `purchase_order_draft` et `stock_picking_draft` restent en brouillon. La confirmation/validation finale demeure dans Odoo sous contrôle humain.

## 4. Relances automatiques

Fuseau `Africa/Casablanca`, du lundi au samedi :

- 07:30 : synthèse des dossiers et propositions ouverts ;
- 16:30 : demande de rapport aux acteurs marqués `daily` ;
- 18:00 : alerte des rapports absents ou incomplets.

Si tous les rapports sont complets ou si aucun chef `daily` n'est enregistré, le job renvoie `NO_REPLY` et ne pollue pas le groupe.

## 5. Commandes utiles

```text
/gotion_status
/gotion_actor add ...
/gotion_actor remove ...
/gotion_approve GOA-...
/gotion_execute GOA-...
```

En conversation normale, on peut aussi demander :

```text
Donne-moi les dossiers de consommation incomplets.
Cherche le produit exact correspondant à AI139 dans Odoo.
Prépare la note Odoo pour la tâche #4107 à partir du dossier GOT-....
```

## 6. États et signification

- `collecting` : informations ou preuves manquantes ;
- `ready_for_review` : dossier complet selon la grille, pas encore validé humainement ;
- `pending_approval` : proposition Odoo préparée, aucune écriture ;
- `approved` : Ahmed a autorisé l'action exacte pour quatre heures ;
- `executed` : écriture réalisée et relue ;
- `expired` : approbation à refaire.

Une information donnée par le chef est `DÉCLARÉ TERRAIN`, pas `CONFIRMÉ`, tant qu'une preuve ou un recoupement n'est pas disponible.
