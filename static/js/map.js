"use strict";

var options = {};
if (start_lat || start_lng) {
  start_lat = start_lat.toFixed(5);
  start_lng = start_lng.toFixed(5);
  options = {
    center: [start_lat, start_lng],
    zoom: zoom,
  };
  history.replaceState(null, null, `/map/${zoom}/${start_lat}/${start_lng}`);
}

var map = L.map("map", options);
var items = {};
var wikidata_items = {};
var osm_objects = {};
var wikidata_loaded = false;
var osm_loaded = false;
var loading = document.getElementById("loading");
var load_text = document.getElementById("load-text");
var isa_card = document.getElementById("isa-card");
var checkbox_list = document.getElementsByClassName("isa-checkbox");
var isa_labels = {};

map.zoomControl.setPosition("topright");

map.on("moveend", function (e) {
  var zoom = map.getZoom();
  var c = map.getCenter();
  var lat = c.lat.toFixed(5);
  var lng = c.lng.toFixed(5);
  history.replaceState(null, null, `/map/${zoom}/${lat}/${lng}`);
});

var blueMarker = L.ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "blue",
  shape: "circle",
  prefix: "fa",
});

var greenMarker = L.ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "green",
  shape: "circle",
  prefix: "fa",
});

var redMarker = L.ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "red",
  shape: "circle",
  prefix: "fa",
});

var osmYellowMarker = L.ExtraMarkers.icon({
  icon: "fa-map",
  markerColor: "yellow",
  shape: "square",
  prefix: "fa",
});

var osmOrangeMarker = L.ExtraMarkers.icon({
  icon: "fa-map",
  markerColor: "orange",
  shape: "square",
  prefix: "fa",
});

if (!start_lat || !start_lng) {
  map.fitBounds([
    [49.85, -10.5],
    [58.75, 1.9],
  ]);
}

var osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
});

osm.addTo(map);

function load_complete() {
  loading.classList.add("visually-hidden");
  load_text.classList.remove("visually-hidden");
}

function add_to_feature_group(qid, thing) {
  if (items[qid] === undefined) items[qid] = {};
  if (items[qid].group === undefined) items[qid].group = L.featureGroup();

  var group = items[qid].group;
  thing.addTo(group);
  return group;
}

function update_wikidata() {
  if (
    Object.keys(wikidata_items).length === 0 ||
    Object.keys(osm_objects).length === 0
  ) {
    if (wikidata_loaded && osm_loaded) load_complete();
    return;
  }

  for (const qid in osm_objects) {
    var osm_list = osm_objects[qid];

    var item = wikidata_items[qid];

    osm_list.forEach((osm) => {
      osm.marker.setIcon(item ? osmYellowMarker : osmOrangeMarker);
    });

    if (!item) continue;

    item.markers.forEach((marker_data) => {
      marker_data.marker.setIcon(greenMarker);
      osm_list.forEach((osm) => {
        var path = [osm.centroid, marker_data];
        var polyline = L.polyline(path, { color: "green" });
        add_to_feature_group(qid, polyline);
      });
    });
  }
  for (const qid in wikidata_items) {
    if (osm_objects[qid]) continue;
    var item = wikidata_items[qid];
    item.markers.forEach((marker_data) => {
      marker_data.marker.setIcon(redMarker);
    });
  }

  load_complete();
}

function isa_only(e) {
  e.preventDefault();

  var this_id = e.target.parentNode.childNodes[0].id;

  for (const checkbox of checkbox_list) {
    checkbox.checked = checkbox.id == this_id;
  }

  checkbox_change();
}

function show_all_isa(e) {
  e.preventDefault();

  for (const checkbox of checkbox_list) {
    checkbox.checked = true;
  }

  checkbox_change();
}

function checkbox_change() {
  var ticked = [];
  for (const checkbox of checkbox_list) {
    if (checkbox.checked) ticked.push(checkbox.id.substr(4));
  }

  for (const qid in items) {
    var item = items[qid];

    if (item.isa_list === undefined) continue;
    const item_isa_list = item.isa_list;
    const intersection = ticked.filter((isa_qid) =>
      item_isa_list.includes(isa_qid)
    );

    if (intersection.length) {
      item.group.addTo(map);
    } else {
      item.group.removeFrom(map);
    }
  }
}

function set_isa_list(isa_count) {
  isa_card.classList.remove("visually-hidden");
  var isa_list = document.getElementById("isa-list");
  isa_list.innerHTML = "";
  isa_count.forEach((isa) => {
    isa_labels[isa.qid] = isa.label;
    var isa_id = `isa-${isa.qid}`;
    var e = document.createElement("div");
    e.setAttribute("class", "isa-item");

    var checkbox = document.createElement("input");
    checkbox.setAttribute("type", "checkbox");
    checkbox.setAttribute("checked", "checked");
    checkbox.setAttribute("id", isa_id);
    checkbox.setAttribute("class", "isa-checkbox");
    checkbox.onchange = checkbox_change;
    e.appendChild(checkbox);

    e.appendChild(document.createTextNode(" "));

    var label = document.createElement("label");
    label.setAttribute("for", isa_id);
    var label_text = document.createTextNode(
      ` ${isa.label} (${isa.qid}): ${isa.count} `
    );
    label.appendChild(label_text);

    e.appendChild(label);
    e.appendChild(document.createTextNode(" "));

    var only = document.createElement("a");
    only.setAttribute("href", "#");
    var only_text = document.createTextNode("only");
    only.appendChild(only_text);
    only.onclick = isa_only;
    e.appendChild(only);

    isa_list.appendChild(e);
  });
}

function add_wikidata_marker(item, marker_data) {
  var icon = blueMarker;
  var qid = item.qid;
  var label = `${item.label} (${item.qid})`;
  var marker = L.marker(marker_data, { icon: icon });
  // var tooltip = marker.bindTooltip(item.qid, {permanent: true, direction: 'bottom', opacity: 0.5});
  var wd_url = "https://www.wikidata.org/wiki/" + item.qid;
  var popup = "<p><strong>Wikidata item</strong><br>";
  popup += `<a href="${wd_url}" target="_blank">${item.label}</a> (${item.qid})`;
  if (item.description) {
    popup += `<br>description: ${item.description}`;
  }
  if (item.isa_list && item.isa_list.length) {
    popup += "<br><strong>item type</strong>";
    for (const [index, isa_qid] of item.isa_list.entries()) {
      var isa_url = "https://www.wikidata.org/wiki/" + isa_qid;
      var isa_label = isa_labels[isa_qid];
      popup += `<br><a href="${isa_url}" target="_blank">${isa_label}</a> (${isa_qid})`;
    }
  }
  if (item.image_list && item.image_list.length) {
    popup += `<br><img src="/commons/${item.image_list[0]}">`;
  }
  popup += "</p>";
  marker.bindPopup(popup);
  var group = add_to_feature_group(item.qid, marker);
  group.addTo(map);
  marker_data.marker = marker;
}

function load_wikidata_items() {
  var checkbox_list = document.getElementsByClassName("isa-checkbox");

  for (const checkbox of checkbox_list) checkbox.checked = true;

  checkbox_change();

  loading.classList.remove("visually-hidden");
  load_text.classList.add("visually-hidden");

  var bounds = map.getBounds();
  console.log("map moved", bounds.toBBoxString());

  var params = { bounds: bounds.toBBoxString() };
  var items_url = "/api/1/items";

  axios.get(items_url, { params: params }).then((response) => {
    set_isa_list(response.data.isa_count);
    var load_items = response.data.items;
    load_items.forEach((item) => {
      var qid = item.qid;
      if (item.qid in wikidata_items) return;
      item.markers.forEach((marker_data) =>
        add_wikidata_marker(item, marker_data)
      );
      wikidata_items[item.qid] = item;

      if (items[qid] === undefined) items[qid] = {};
      items[qid].isa_list = item.isa_list;
    });

    wikidata_loaded = true;
    isa_card.classList.remove("visually-hidden");
    update_wikidata();
  });
  var osm_objects_url = "/api/1/osm";
  axios.get(osm_objects_url, { params: params }).then((response) => {
    console.log(`${response.data.duration} seconds`);
    response.data.objects.forEach((osm) => {
      var qid = osm.wikidata;
      if (osm_objects[qid] === undefined) osm_objects[qid] = [];
      osm_objects[qid].push(osm);

      var icon = osmYellowMarker;
      var marker = L.marker(osm.centroid, { title: osm.name, icon: icon });
      osm.marker = marker;
      var wd_url = "https://www.wikidata.org/wiki/" + qid;
      var popup = `
      <p>
        ${osm.name}:
        <a href="${osm.url}" target="_blank">${osm.identifier}</a>
        <br>
        Wikidata tag: <a href="${wd_url}" target="_blank">${qid}</a>
      </p>`;
      marker.bindPopup(popup);
      var group = add_to_feature_group(qid, marker);
      group.addTo(map);

      if (osm.type != "node" && osm.geojson) {
        var mapStyle = { fillOpacity: 0 };
        var geojson = L.geoJSON(null, { style: mapStyle });
        geojson.addData(osm.geojson);
        add_to_feature_group(qid, geojson);
      }
    });

    osm_loaded = true;
    update_wikidata();
  });
}

document.getElementById("search-form").onsubmit = function (e) {
  e.preventDefault();
  var search_text = document.getElementById("search-text").value.trim();
  if (!search_text) return;
  var params = { q: search_text };
  var search_url = "/api/1/search";
  var search_results = document.getElementById("search-results");
  axios.get(search_url, { params: params }).then((response) => {
    search_results.innerHTML = "";
    response.data.hits.forEach((hit) => {
      var e = document.createElement("div");
      var category = document.createTextNode(hit.category + " ");
      e.appendChild(category);
      var a = document.createElement("a");
      var lat = parseFloat(hit.lat).toFixed(5);
      var lon = parseFloat(hit.lon).toFixed(5);
      a.setAttribute("href", `/map/15/${lat}/${lon}`);
      var link_text = document.createTextNode(hit.name);
      a.appendChild(link_text);
      e.appendChild(a);
      search_results.appendChild(e);
    });
  });
};

document.getElementById("load-btn").onclick = load_wikidata_items;
document.getElementById("show-all-isa").onclick = show_all_isa;
