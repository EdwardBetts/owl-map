'use strict';

var map = L.map('map');

var tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png');
var group = L.featureGroup();
map.addLayer(group);
tiles.addTo(map);

var items = {};
var duration_span = document.getElementById("duration");

map.on('moveend', function(e) {
  var bounds = map.getBounds();
  console.log("map moved", bounds.toBBoxString());

  var markers_url = "/api/1/markers.json";
  var params = {bounds: bounds.toBBoxString()};
  axios.get(markers_url, {params: params}).then(response => {
    var items = response.data.items;
    items.forEach(item => {
        if (item.qid in items)
            return;
        item.markers.forEach(marker => {
            var marker = L.marker(marker, {"title": item.label });
            marker.addTo(group);
        });
        items[item.qid] = item;
    });

    duration_span.innerText = response.data.duration;


  });

});

var hit_links = document.getElementsByClassName("hit-link");

// console.log(hit_links);

for (const link of hit_links) {
  link.addEventListener('click', event => {
    event.preventDefault();
    var link = event.target;
    var id_string = event.target.id;
    var re_id = /^hit-link-(\d+)$/;
    var hit_index = re_id.exec(id_string)[1];
    var [south, north, west, east] = bbox_list[hit_index];
    var bounds = [[north, west], [south, east]];

    console.log('click', bounds);
    map.fitBounds(bounds);
  });
}
