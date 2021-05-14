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
var detail_card = document.getElementById("detail-card");
var detail = document.getElementById("detail");
var detail_image = document.getElementById("detail-image");
var detail_header = document.getElementById("detail-header");
var search_and_isa = document.getElementById("search-and-isa");
var detail_qid;
var candidates = document.getElementById("candidates");
var checkbox_list = document.getElementsByClassName("isa-checkbox");
var nearby_lookup = {};
var isa_labels = {};
var items_url = "/api/1/items";
var osm_objects_url = "/api/1/osm";
var missing_url = "/api/1/missing";
var hover_circles = [];
var selected_circles = [];
var candidate_outline;

var isa_count = {};

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
  loading.classList.add("d-none");
  load_text.classList.remove("d-none");
  detail_card.classList.add("d-none");
}

function add_to_feature_group(qid, thing) {
  if (items[qid] === undefined) items[qid] = {};
  if (items[qid].group === undefined) items[qid].group = L.featureGroup();

  var group = items[qid].group;
  thing.addTo(group);
  return group;
}

function update_wikidata(check_for_missing = true) {
  if (
    Object.keys(wikidata_items).length === 0 ||
    Object.keys(osm_objects).length === 0
  ) {
    if (wikidata_loaded && osm_loaded) load_complete();
    return;
  }

  if (check_for_missing) {
    var missing_qids = [];
    for (const qid in osm_objects) {
      var item = wikidata_items[qid];
      if (!item) missing_qids.push(qid);
    }

    if (missing_qids.length) {
      var params = { qids: missing_qids.join(",") };
      axios.get(missing_url, { params: params }).then((response) => {
        response.data.isa_count.forEach((isa) => {
          isa_labels[isa.qid] = isa.label;
          if (isa_count[isa.qid] === undefined) {
            isa_count[isa.qid] = isa;
          } else {
            isa_count[isa.qid].count += 1;
          }
        });

        process_wikidata_items(response.data.items);
        update_wikidata(false);
      });
    }
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
      if (!items[qid].lines) items[qid].lines = [];
      osm_list.forEach((osm) => {
        var path = [osm.centroid, marker_data];
        var polyline = L.polyline(path, { color: "green" });
        add_to_feature_group(qid, polyline);
        items[qid].lines.push(polyline);
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

  var isa_count_values = Object.values(isa_count);
  set_isa_list(isa_count_values);
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
    if (item.group === undefined) continue;

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

function set_isa_list(isa_count_list) {
  isa_count_list.sort((a, b) => b.count - a.count);

  isa_card.classList.remove("d-none");
  var isa_list = document.getElementById("isa-list");
  isa_list.innerHTML = "";
  isa_count_list.forEach((isa) => {
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

function build_item_detail(item, tag_or_key_list) {
  var wd_url = "https://www.wikidata.org/wiki/" + item.qid;
  var popup = '<div class="row"><div class="col">'

  popup += "<strong>Wikidata item</strong><br>";
  popup += `<a href="${wd_url}" target="_blank">${item.label}</a> (${item.qid})`;
  if (item.description) {
    popup += `<br><strong>description</strong><br>${item.description}`;
  }
  if (item.isa_list && item.isa_list.length) {
    popup += "<br><strong>item type</strong>";
    for (const [index, isa_qid] of item.isa_list.entries()) {
      var isa_url = "https://www.wikidata.org/wiki/" + isa_qid;
      var isa_label = isa_labels[isa_qid];
      popup += `<br><a href="${isa_url}" target="_blank">${isa_label}</a> (${isa_qid})`;
    }
  }
  popup += '</div><div class="col">'

  if (tag_or_key_list && tag_or_key_list.length) {
    popup += "<br><strong>OSM tags/keys to search for</strong>";
    for (const v of tag_or_key_list) {
      popup += `<br>${v}`;
    }
  }

  if (item.street_address && item.street_address.length) {
    popup += "<br><strong>street address</strong>";
    popup += `<br>${item.street_address[0]["text"]}`;
  }

  popup += "</div></div>";

  return popup;
}

function mouseover(item) {
  if (item.outline) {
    item.outline.setStyle({ fillOpacity: 0.2, weight: 6 });
  }
  if (item.lines) {
    item.lines.forEach((line) => {
      line.setStyle({ weight: 6 });
    });
  }

  item.markers.forEach((marker) => {
    var coords = marker.getLatLng();
    var circle = L.circle(coords, { radius: 20 }).addTo(map);
    hover_circles.push(circle);
  });
}

function mouseout(item) {
  if (item.outline) {
    item.outline.setStyle({ fillOpacity: 0, weight: 3 });
  }
  if (item.lines) {
    item.lines.forEach((line) => {
      line.setStyle({ weight: 3 });
    });
  }

  hover_circles.forEach((circle) => {
    circle.removeFrom(map);
  });
  hover_circles = [];
}

function close_item_details() {
  selected_circles.forEach((circle) => {
    circle.removeFrom(map);
  });
  selected_circles = [];

  detail_header.innerHTML = "";
  detail.innerHTML = "";
  candidates.innerHTML = "";
  detail_qid = undefined;

  detail_image.setAttribute("src", "");
  detail_image.classList.add("d-none");

  if (candidate_outline) {
    candidate_outline.removeFrom(map);
    candidate_outline = undefined;
  }
}

function show_outline(osm) {
    if (candidate_outline !== undefined) {
      candidate_outline.removeFrom(map);
    }

    var mapStyle = { fillOpacity: 0, color: "red" };
    var geojson = L.geoJSON(null, { style: mapStyle });
    geojson.addData(osm.geojson);
    geojson.addTo(map);

    candidate_outline = geojson;
}

function mouse_events(marker, qid) {
  items[qid] ||= {};
  var item = items[qid];
  marker.on("mouseover", function () {
    mouseover(item);
  });
  marker.on("mouseout", function () {
    mouseout(item);
  });
  marker.on("click", function () {
    var wd_item = items[qid].wikidata;
    search_and_isa.classList.add("d-none");
    detail_card.classList.remove("d-none");
    detail_card.classList.add("bg-highlight");
    close_item_details();

    item.markers.forEach((marker) => {
      var coords = marker.getLatLng();
      var circle = L.circle(coords, { radius: 20, color: "orange" }).addTo(map);
      selected_circles.push(circle);
    });

    window.setTimeout(function () {
      detail_card.classList.remove("bg-highlight");
    }, 500);

    detail_qid = qid;

    if (wd_item.image_list && wd_item.image_list.length) {
      detail_image.setAttribute("src", `/commons/${wd_item.image_list[0]}`);
      detail_image.classList.remove("d-none");
    } else {
      detail_image.setAttribute("src", "");
      detail_image.classList.add("d-none");
    }

    var item_label = `${wd_item.label} (${wd_item.qid})`;
    detail_header.innerHTML = "";
    detail_header.append(document.createTextNode(item_label));

    var item_tags_url = `/api/1/item/${qid}/tags`;
    axios.get(item_tags_url).then((response) => {
      var tag_or_key_list = response.data.tag_or_key_list;
      if (response.data.qid != detail_qid) {
        tag_or_key_list = []; // different QID
      }
      var item_detail = build_item_detail(wd_item, tag_or_key_list);
      detail.innerHTML = item_detail;

      if (tag_or_key_list.length == 0) return;

      var item_osm_candidates_url = `/api/1/item/${qid}/candidates`;
      var bounds = map.getBounds();

      var params = { bounds: bounds.toBBoxString() };

      axios
        .get(item_osm_candidates_url, { params: params })
        .then((response) => {
          if (response.data.qid != detail_qid) return; // different QID
          var nearby = response.data.nearby;
          if (!nearby.length) return;
          var osm_html = "<strong>Possible OSM matches</strong><br>";
          for (const osm of nearby) {
            var span_id = osm.identifier.replace("/", "_");
            nearby_lookup[span_id] = osm;
            osm_html += `<span class="osm-candidate" id="${span_id}"> ${osm.distance.toFixed(0)}m `
            osm_html += osm.presets.map(function(p) {
              var wiki_url = `http://wiki.openstreetmap.org/wiki/${p.tag_or_key}`;
              return `<a href="${wiki_url}" class="osm-wiki-link" target="_blank">${p.name} <i class="fa fa-external-link"></i></a>`;
            }).join(", ");
            if (osm.presets.length && osm.name) {
              osm_html += ": ";
            }
            if (osm.name) {
              osm_html += osm.name;
            }
            if (!osm.presets.length && !osm.name) {
              osm_html += "no name";
            }
            osm_html += ` <a href="https://www.openstreetmap.org/${osm.identifier}" target="_blank">`
            osm_html += '<i class="fa fa-map-o"></i></a></span><br>';
          }
          candidates.innerHTML = osm_html;
          var span_list = document.getElementsByClassName("osm-candidate");

          for (const osm_span of span_list) {
            osm_span.onmouseenter = function (e) {
              show_outline(nearby_lookup[e.target.id]);
            };
          }
        });
    });
  });

  item.markers ||= [];
  item.markers.push(marker);
}

function add_wikidata_marker(item, marker_data) {
  var icon = blueMarker;
  var qid = item.qid;
  var label = `${item.label} (${item.qid})`;
  var marker = L.marker(marker_data, { icon: icon });
  mouse_events(marker, qid);

  var group = add_to_feature_group(item.qid, marker);
  group.addTo(map);
  items[qid].wikidata = item;

  marker_data.marker = marker;
}

function process_wikidata_items(load_items) {
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
}

function load_wikidata_items() {
  var checkbox_list = document.getElementsByClassName("isa-checkbox");

  for (const checkbox of checkbox_list) checkbox.checked = true;

  checkbox_change();

  close_item_details();
  detail_card.classList.add("d-none");
  loading.classList.remove("d-none");
  load_text.classList.add("d-none");

  var bounds = map.getBounds();

  var params = { bounds: bounds.toBBoxString() };

  axios.get(items_url, { params: params }).then((response) => {
    response.data.isa_count.forEach((isa) => {
      isa_count[isa.qid] = isa;
      isa_labels[isa.qid] = isa.label;
    });

    process_wikidata_items(response.data.items);

    wikidata_loaded = true;
    isa_card.classList.remove("d-none");
    update_wikidata();
  });

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
      // marker.bindPopup(popup);
      mouse_events(marker, qid);

      var group = add_to_feature_group(qid, marker);
      group.addTo(map);
      items[qid].markers ||= [];
      items[qid].markers.push(marker);

      if (osm.type != "node" && osm.geojson) {
        var mapStyle = { fillOpacity: 0 };
        var geojson = L.geoJSON(null, { style: mapStyle });
        geojson.addData(osm.geojson);
        add_to_feature_group(qid, geojson);
        items[qid].outline = geojson;
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

function close_detail() {
  search_and_isa.classList.remove("d-none");
  detail_card.classList.add("d-none");

  close_item_details();
}

document.getElementById("load-btn").onclick = load_wikidata_items;
document.getElementById("show-all-isa").onclick = show_all_isa;
document.getElementById("close-detail").onclick = close_detail;
