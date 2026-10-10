// Comportements communs à toutes les pages
document.addEventListener('DOMContentLoaded', function () {
  // Menu latéral sur téléphone
  var bouton = document.getElementById('ouvrir-menu');
  if (bouton) {
    bouton.addEventListener('click', function () { document.body.classList.toggle('menu-ouvert'); });
  }

  // Les messages de succès disparaissent seuls
  setTimeout(function () {
    document.querySelectorAll('.message.succes, .message.info').forEach(function (m) { m.remove(); });
  }, 6000);

  // Tableaux filtrables : <table data-filtrable> avec un champ [data-recherche] et des boutons [data-filtre]
  document.querySelectorAll('table[data-filtrable]').forEach(function (tableau) {
    var zone = tableau.closest('.panneau');
    var recherche = zone.querySelector('[data-recherche]');
    var boutons = zone.querySelectorAll('[data-filtre]');
    var filtre = '';

    function appliquer() {
      var texte = recherche ? recherche.value.trim().toLowerCase() : '';
      tableau.querySelectorAll('tbody tr[data-etat]').forEach(function (ligne) {
        var visible = (!filtre || ligne.dataset.etat === filtre) &&
                      (!texte || ligne.textContent.toLowerCase().indexOf(texte) !== -1);
        ligne.hidden = !visible;
      });
    }

    if (recherche) { recherche.addEventListener('input', appliquer); }
    boutons.forEach(function (b) {
      b.addEventListener('click', function () {
        boutons.forEach(function (autre) { autre.classList.remove('actif'); });
        b.classList.add('actif');
        filtre = b.dataset.filtre;
        appliquer();
      });
    });
  });
});
