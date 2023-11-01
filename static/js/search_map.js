'use strict';

// Create a map

var options = {};
if (user_lat && user_lon) {
  options = {
    center: [user_lat, user_lon],
    zoom: 15,
  };
}

var map = L.map("map", options);
map.zoomControl.setPosition('topright');

if (!user_lat || !user_lon) {
  map.fitBounds([[49.85,-10.5], [58.75, 1.9]]);
}

// Add OpenStreetMap layer
var osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 });

osm.addTo(map);

var hits = document.getElementsByClassName("hit-card");
var current_hit = null;

for (const card of hits) {
  card.addEventListener('mouseover', event => {
    var id_string = card.id;
    if (current_hit == id_string) return;
    current_hit = id_string;
    var re_id = /^hit-card-(\d+)$/;
    var hit_index = re_id.exec(id_string)[1];
    var [south, north, west, east] = bbox_list[hit_index];
    var bounds = [[north, west], [south, east]];

    map.fitBounds(bounds);
  });
}
