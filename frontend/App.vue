<template>
<div>

  <nav id="nav" class="navbar navbar-expand navbar-light bg-light">
    <div class="container-fluid">
      <a class="navbar-brand" href="/">osm.wikidata.link</a>
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">
        <li class="nav-item">
          <a class="nav-link active" aria-current="page" href="#">Home</a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="#">Link</a>
        </li>
        <li class="nav-item dropdown">
          <a class="nav-link dropdown-toggle" href="#" id="navbarDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
            Dropdown
          </a>
          <ul class="dropdown-menu" aria-labelledby="navbarDropdown">
            <li><a class="dropdown-item" href="#">Action</a></li>
            <li><a class="dropdown-item" href="#">Another action</a></li>
            <li><hr class="dropdown-divider"></li>
            <li><a class="dropdown-item" href="#">Something else here</a></li>
          </ul>
        </li>
        <li class="nav-item">
          <a class="nav-link disabled" href="#" tabindex="-1" aria-disabled="true">Disabled</a>
        </li>
      </ul>
      <ul class="navbar-nav">
        <li class="nav-item">
          <a v-if="username" class="nav-link" href="#">{{ username }}</a>
          <a v-else class="nav-link" href="/login">Login</a>
        </li>
      </ul>
    </div>
  </nav>

  <div id="map">
  </div>

  <button ref="btn" id="load-btn" type="button" class="btn btn-primary btn-lg" @click="load_wikidata_items">
    <span v-if="!loading">
      Load Wikidata items
    </span>
    <span v-if="loading">
    <span class="spinner-border spinner-border-sm"></span>
      Loading ...
    </span>
  </button>

  <div id="edit-count" class="p-2" v-if="edits.length">
    <span>edits: {{ edits.length }}</span>
    <button class="btn btn-primary btn-sm ms-2" @click="close_item(); view_edits=true">
      <i class="fa fa-upload"></i> save
    </button>
  </div>

  <div v-if="current_item && wd_item.image_list.length" class="modal fade" id="imageModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">Image from Wikidata</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <img class="img-fluid" :src="api_base_url + '/commons/' + wd_item.image_list[0]">
        </div>
      </div>
    </div>
  </div>

  <div id="sidebar">
    <div v-if="view_edits" class="p-2">
      <div class="h3">
        Upload to OpenStreetMap
        <button type="button" class="btn-close float-end" @click="view_edits=false"></button>
      </div>

      <div class="card w-100 bg-light">
        <div class="card-body">
          <form>
            <div class="mb-3">
              <label for="changesetComment" class="form-label">Changeset comment</label>
              <input type="text" class="form-control" id="changesetComment" :value="changeset_comment">
            </div>
            <button type="submit" class="btn btn-primary">Upload tags</button>
          </form>
        </div>
      </div>

      <div>
        <div>
          <div class="card my-2 w-100" v-for="edit in edits_grouped_by_qid">
            <div class="card-body">
              <h4 class="card-title">
                <a :href="qid_url(edit.qid)" target="_blank">
                  {{ edit.wikidata.label }}
                </a> ({{ edit.qid }})
              </h4>

              <p class="card-text">

              <span v-if="edit.wikidata.description">
                <strong>description</strong><br/>
                {{ edit.wikidata.description }}<br/>
              </span>

              <strong>item type</strong><br/>
              <span
                  v-bind:key="`isa-${edit.qid}-${isa_qid}`"
                  v-for="isa_qid in edit.wikidata.isa_list">
                <a :href="qid_url(isa_qid)" target="_blank">{{isa_labels[isa_qid]}}</a> ({{isa_qid}})
                <br/>
              </span>

              <span v-if="edit.wikidata.street_address.length">
                <strong>street address</strong><br/>
                {{ edit.wikidata.street_address[0] }}<br/>
              </span>

              <strong>OSM matches</strong>

              </p>

              <table class="table table-sm table-hover">
                <tbody>
                  <tr v-for="osm in edit.osm" class="osm-candidate">
                    <td class="text-end text-nowrap">
                      {{ osm.distance.toFixed(0) }}m
                      <a
                        :href="'https://www.openstreetmap.org/' + osm.identifier"
                        target="_blank"
                        @click.stop><i class="fa fa-map-o"></i></a>
                    </td>
                    <td>
                    {{ osm.name || "no name" }}
                    <span v-for="(p, index) in osm.presets">
                      <span v-if="index != 0">, </span>
                      <a
                        :href="'http://wiki.openstreetmap.org/wiki/' + p.tag_or_key"
                        class="osm-wiki-link"
                        target="_blank"
                        @click.stop>{{p.name}} <i class="fa fa-external-link"></i></a>
                    </span>

                    <span v-if="osm.address && osm.address != osm.name">
                        <br>street address: {{ osm.address }}
                    </span>
                    <span v-else-if="osm.tags['addr:street'] && osm.address != osm.name">
                        <br>street: {{ osm.tags['addr:street'] }}
                    </span>

                    <span v-if="osm.address_list.length">
                        <br>address nodes: {{ osm.address_list.join("; ") }}
                    </span>

                    <span v-if="osm.part_of">
                        <br>part of: {{ osm.part_of.join("; ") }}
                    </span>

                    <br>
                      <span v-if="osm.selected">
                        add tag: <span class="badge bg-success">wikidata={{ edit.qid }}</span>
                      </span>
                      <span v-else>
                        remove tag: <span class="badge bg-danger">wikidata={{ edit.qid }}</span>
                      </span>

                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!current_item && !view_edits">

      <div class="card m-2">
        <div class="card-body">
          <form id="search-form" class="row row-cols-lg-auto g-3 align-items-center" @submit.prevent="run_search">
            <div class="col-12">
              <input class="form-control" id="search-text" v-model.trim="search_text" placeholder="place">
            </div>
            <div class="col-12">
              <button type="submit" id="search-btn" class="btn btn-primary">search</button>
            </div>
          </form>
          <div class="list-group" v-if="hits.length">
            <a class="list-group-item list-group-item-action"
                :class="{ active: hit.identifier == this.active_hit }"
                v-bind:key="hit.identifier"
                v-for="hit in hits"
                :href="hit_url(hit)"
                @click.prevent="visit(hit)">
              {{ hit.name }} ({{ hit.category }})
            </a>
          </div>
        </div>
      </div>


      <div class="card m-2" v-if="!view_edits && isa_list.length">
        <div class="card-body">
          <div class="h5 card-title">OSM/Wikidata link status</div>
          <div class="list-group">
            <label for="linked" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center">
              <span>
                <input class="form-check-input me-1" id="linked" type="checkbox" v-model="linked">
                Wikidata items tagged in OSM
              </span>
              <span class="badge bg-primary rounded-pill">{{ tagged_count }}</span>
            </label><br>
            <label for="not-linked" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center">
              <span>
                <input class="form-check-input me-1" id="not-linked" type="checkbox" v-model="not_linked">
                Wikidata items not tagged in OSM
              </span>
              <span class="badge bg-primary rounded-pill">{{ not_tagged_count }}</span>
            </label>
          </div>
        </div>
      </div>

      <div class="card m-2" v-if="!view_edits && isa_list.length" id="isa-card">
        <div class="card-body">
          <div class="h5 card-title">item types</div>
          <div><a href="#" @click.prevent="isa_tick_all">show all</a></div>

          <div class="list-group" @mouseout="this.hover_isa=undefined">
            <label class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" v-for="isa in isa_list" @mouseenter="this.hover_isa=isa">
              <span>
              <input class="form-check-input me-1" type="checkbox" :id="'isa-' + isa.qid" :value="isa.qid" v-model="isa_ticked">
              {{ isa.label }} ({{ isa.qid }})
              <a href="#" @click.stop="isa_ticked=[isa.qid]">only</a>
              </span>
              <span class="badge bg-primary rounded-pill">{{ isa.count }}</span>
            </label>
          </div>

        </div>
      </div>
    </div>

    <div class="card m-2" id="detail-card" v-if="current_item">
      <div class="card-body">
        <div class="h4 card-title">
          <span id="detail-header">item detail</span>
          <button type="button" class="btn-close float-end" id="close-detail" @click="close_item()"></button>
        </div>
        <div id="detail">
          <div class="row"><div class="col">
          <strong>Wikidata item</strong><br>
          <a :href="qid_url(wd_item.qid)" target="_blank">{{ wd_item.label }}</a> ({{ wd_item.qid }})

          <span v-if="wd_item.description">
            <br><strong>description</strong><br>{{ wd_item.description }}
          </span>

          <br><strong>item type</strong>
          <span v-bind:key="`isa-${wd_item.qid}-${isa_qid}`" v-for="isa_qid in wd_item.isa_list">
            <br><a :href="qid_url(isa_qid)" target="_blank">{{isa_labels[isa_qid]}}</a> ({{isa_qid}})
          </span>

          <span v-if="wd_item.street_address.length">
            <br><strong>street address</strong>
            <br>{{wd_item.street_address[0]}}
          </span>

          </div>
          <div class="col">

          <div v-if="current_item.tag_or_key_list && current_item.tag_or_key_list.length">
            <strong>OSM tags/keys to search for</strong><br/>
            {{ current_item.tag_or_key_list.length }} tags/keys to consider
            <a href="#" @click="show_tag_or_key_list = !show_tag_or_key_list">show/hide</a><br/>
            <div v-if="show_tag_or_key_list">
              <div v-for="v in current_item.tag_or_key_list">{{ v }}</div>
            </div>
          </div>

          <span v-if="wd_item.image_list.length">
            <a href="#" data-bs-toggle="modal" data-bs-target="#imageModal">
              <img class="w-100" :src="api_base_url + '/commons/' + wd_item.image_list[0]">
            </a>
            <br/>
            <a href="#" data-bs-toggle="modal" data-bs-target="#imageModal">
              enlarge image
            </a>
          </span>

        </div></div>
        </div>

        <div v-if="current_item.nearby && current_item.nearby.length">
          <strong>Possible OSM matches</strong><br>
          <table class="table table-sm table-hover">
            <tbody>
              <tr
                  v-for="osm in current_item.nearby"
                  class="osm-candidate"
                  :class="{ 'table-primary': osm.selected }"
                  @mouseenter="this.current_osm=osm"
                  @click="select_osm(current_item, osm)">
                <td>
                  <input class="form-check-input" type="checkbox" v-model="osm.selected"/>
                </td>
                <td class="text-end text-nowrap">
                  {{ osm.distance.toFixed(0) }}m
                  <a
                    :href="'https://www.openstreetmap.org/' + osm.identifier"
                    target="_blank"
                    @click.stop><i class="fa fa-map-o"></i></a>
                </td>
                <td>
                {{ osm.name || "no name" }}
                <span v-for="(p, index) in osm.presets">
                  <span v-if="index != 0">, </span>
                  <a
                    :href="'http://wiki.openstreetmap.org/wiki/' + p.tag_or_key"
                    class="osm-wiki-link"
                    target="_blank"
                    @click.stop>{{p.name}} <i class="fa fa-external-link"></i></a>
                </span>

                <span v-if="osm.address && osm.address != osm.name">
                    <br>street address: {{ osm.address }}
                </span>
                <span v-else-if="osm.tags['addr:street'] && osm.address != osm.name">
                    <br>street: {{ osm.tags['addr:street'] }}
                </span>

                <span v-if="osm.address_list.length">
                    <br>address nodes: {{ osm.address_list.join("; ") }}
                </span>

                <span v-if="osm.part_of">
                    <br>part of: {{ osm.part_of.join("; ") }}
                </span>

                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script>
import L from "leaflet";
import { ExtraMarkers } from "leaflet-extra-markers";
import axios from "redaxios";

var redMarker = ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "red",
  shape: "circle",
  prefix: "fa",
});

var greenMarker = ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "green",
  shape: "circle",
  prefix: "fa",
});

var blueMarker = ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "blue",
  shape: "circle",
  prefix: "fa",
});

var osmYellowMarker = ExtraMarkers.icon({
  icon: "fa-map",
  markerColor: "yellow",
  shape: "square",
  prefix: "fa",
});

export default {
  props: {
    startLat: Number,
    startLon: Number,
    startZoom: Number,
    username: String,
  },
  data() {
    return {
      api_base_url: "https://alpha.osm.wikidata.link",
      tag_or_key_list: [],
      search_text: "",
      load_button_pressed: false,
      hits: [],
      center: undefined,
      zoom: undefined,
      isa_ticked: [],
      isa_list: [],
      isa_lookup: {},
      items: {},
      yellowMarker: osmYellowMarker,
      osm_loaded: false,
      wikidata_loaded: false,
      osm_loading: false,
      wikidata_loading: false,
      current_item: undefined,
      current_osm: undefined,
      hover_qid: undefined,
      isa_labels: {},
      linked: true,
      not_linked: true,
      map: undefined,
      hover_circles: [],
      candidate_outline: undefined,
      check_for_missing_done: false,
      selected_circles: [],
      hover_isa: undefined,
      detail_qid: undefined,
      show_tag_or_key_list: undefined,
      edits: [],
      view_edits: false,
      changeset_comment: "Add wikidata tag",
    };
  },
  computed: {
    loading() {
      return this.osm_loading || this.wikidata_loading;
    },
    wd_item() {
      return this.current_item ? this.current_item.wikidata : undefined;
    },
    tagged_count() {
      var count = 0;
      for (const qid in this.items) {
        var item = this.items[qid];
        if (item.wikidata && item.osm) {
          count += 1;
        }
      }
      return count;
    },
    not_tagged_count() {
      var count = 0;
      for (const qid in this.items) {
        var item = this.items[qid];
        if (item.wikidata && !item.osm) {
          count += 1;
        }
      }
      return count;
    },
    selected_items() {
      var ret = {};
      for (const qid in this.items) {
        var item = this.items[qid];
        if (!item.wikidata) continue;

        if (!this.linked && item.osm) continue;
        if (!this.not_linked && !item.osm) continue;

        if (item.wikidata.isa_list.some(isa => this.isa_ticked.includes(isa))) {
          ret[qid] = item;
        }
      }
      return ret;
    },
    edits_grouped_by_qid() {
      var qid_order = [];
      var edit_lookup = {};

      this.edits.forEach((edit) => {
        var qid = edit.item.qid;

        if (!edit_lookup[qid]) {
          qid_order.push(qid);
          console.log(edit.item);
          edit_lookup[qid] = {
            'qid': qid,
            'wikidata': edit.item.wikidata,
            'osm': [],
          }
        }

        edit_lookup[qid].osm.push(edit.osm);
      });

      return qid_order.map((qid) => edit_lookup[qid]);
    },
  },
  watch: {
    selected_items(new_items, old_items) {
      for (const qid of Object.keys(new_items)) {
        if (!old_items[qid])
          this.items[qid].group.addTo(this.map);
      }

      for (const qid of Object.keys(old_items)) {
        if (!new_items[qid])
          this.items[qid].group.removeFrom(this.map);
      }
    },
    current_osm(osm) {
      if (this.candidate_outline !== undefined) {
        this.candidate_outline.removeFrom(this.map);
      }

      if (osm === undefined) return;

      var mapStyle = { fillOpacity: 0, color: "red" };
      var geojson = L.geoJSON(null, { style: mapStyle });
      geojson.addData(osm.geojson);
      geojson.addTo(this.map);

      this.candidate_outline = geojson;
    },
    current_item(item, old_item) {
      if (old_item) {
        this.selected_circles.forEach((circle) => {
          circle.removeFrom(this.map);
        });
      }

      this.selected_circles = [];

      if (!item) return;

      item.markers.forEach((marker) => {
        var coords = marker.getLatLng();
        var circle = L.circle(coords, { radius: 20, color: "orange" }).addTo(this.map);
        this.selected_circles.push(circle);
      });

    },
    hover_isa(highlight_isa) {
      this.drop_hover_circles();

      for(const item of Object.values(this.selected_items)) {
        var opacity = 0.9;
        if (highlight_isa) {
          var match = item.wikidata.isa_list.some(isa => isa == highlight_isa.qid);
          opacity = match ? 1 : 0.2;
          if (match) {
            this.add_hover_circles(item);
          }
        }
        this.set_item_opacity(item, opacity);

      }
    }
  },
  methods: {
    edit_list_index(item, osm) {
      var index = -1;
      for (var i = 0; i < this.edits.length; i++) {
        var edit = this.edits[i];
        if (edit.item.qid == item.qid &&
            edit.osm.identifier == osm.identifier) {
          index = i;
          break;
        }
      }
      return index;
    },
    select_osm(item, osm) {
      osm.selected = !osm.selected;
      var index = this.edit_list_index(item, osm);

      if (index == -1) {
        this.edits.push({'item': item, 'osm': osm});
      } else {
        this.edits.splice(index, 1);
      }
    },
    qid_from_url() {
      const queryString = window.location.search;
      const urlParams = new URLSearchParams(queryString);
      return urlParams.get("item") || undefined;
    },
    isa_tick_all() {
      this.isa_ticked = Object.keys(this.isa_labels);
    },
    build_map_path() {
      var zoom = this.map.getZoom();
      var c = this.map.getCenter();
      var lat = c.lat.toFixed(5);
      var lng = c.lng.toFixed(5);
      var path = `/map/${zoom}/${lat}/${lng}`;
      if (this.current_item) {
        path += `?item=${this.wd_item.qid}`;
      }
      return path;
    },

    mouse_events(marker, qid) {
      marker.on("mouseover", () => { this.add_highlight(qid); });
      marker.on("mouseout", () => { this.drop_highlight(qid); });
      marker.on("click", () => { this.open_item(qid); });

      var item = this.items[qid];

      item.markers ||= [];
      item.markers.push(marker);
    },

    set_item_opacity(item, opacity) {
      if (item.outline) {
        item.outline.setStyle({ opacity: opacity });
      }
      if (item.lines) {
        item.lines.forEach((line) => {
          line.setStyle({ opacity: opacity });
        });
      }

      item.markers.forEach((marker) => {
        marker.setOpacity(opacity);
      })

    },

    add_hover_circles(item) {
      item.markers.forEach((marker) => {
        var coords = marker.getLatLng();
        var circle = L.circle(coords, { radius: 20 }).addTo(this.map);
        this.hover_circles.push(circle);
      });
    },
    drop_hover_circles() {
      this.hover_circles.forEach((circle) => {
        circle.removeFrom(this.map);
      });
      this.hover_circles = [];
    },
    add_highlight(qid) {
      var item = this.items[qid];

      if (item.outline) {
        item.outline.setStyle({ fillOpacity: 0.2, weight: 6 });
      }
      if (item.lines) {
        item.lines.forEach((line) => {
          line.setStyle({ weight: 6 });
        });
      }
      this.add_hover_circles(item);
    },
    drop_highlight(qid) {
      var item = this.items[qid];

      if (item.outline) {
        item.outline.setStyle({ fillOpacity: 0, weight: 3 });
      }
      if (item.lines) {
        item.lines.forEach((line) => {
          line.setStyle({ weight: 3 });
        });
      }
      this.drop_hover_circles();
    },
    update_map_path() {
      history.replaceState(null, null, this.build_map_path());
    },
    open_item(qid) {
      var item = this.items[qid];
      this.view_edits = false;
      this.current_osm = undefined;
      this.current_item = item;
      this.update_map_path();
      this.hover_isa = undefined;

      if (item.detail_requested !== undefined) return;
      item.detail_requested = true;

      var item_tags_url = `${this.api_base_url}/api/1/item/${qid}/tags`;
      axios.get(item_tags_url).then((response) => {
        var qid = response.data.qid;
        this.items[qid].tag_or_key_list = response.data.tag_or_key_list;
      });

      var item_osm_candidates_url = `${this.api_base_url}/api/1/item/${qid}/candidates`;
      var bounds = this.map.getBounds();
      var params = { bounds: bounds.toBBoxString() };

      axios.get(item_osm_candidates_url, { params: params }).then((response) => {
        var qid = response.data.qid;
        var item = this.items[qid];
        var osm_identifiers = []

        if (item.osm) {
          item.osm.forEach((osm) => { osm_identifiers.push(osm.identifier); });
        }

        item.nearby = response.data.nearby;
        item.nearby.forEach((osm) => {
          osm.selected = osm_identifiers.includes(osm.identifier);
          if (this.edits.length && this.edit_list_index(item, osm) != -1) {
            osm.selected = !osm.selected;
          }
        });
      });
    },
    close_item() {
      this.current_osm = undefined;
      this.current_item = undefined;
      this.update_map_path();
    },
    qid_url(qid) {
      return "https://www.wikidata.org/wiki/" + qid;
    },
    getMarker(item) {
      if (!this.osm_loaded) return blueMarker;
      return item.osm ? greenMarker : redMarker;
    },
    hit_url(hit) {
      var lat = parseFloat(hit.lat).toFixed(5);
      var lon = parseFloat(hit.lon).toFixed(5);
      return `/map/16/${lat}/${lon}`
    },
    visit(hit) {
      var lat = parseFloat(hit.lat).toFixed(5);
      var lon = parseFloat(hit.lon).toFixed(5);

      this.map.setView([lat, lon], 16);
      this.auto_load();
    },

    process_wikidata_items(load_items) {
      load_items.forEach(item => {
        var qid = item.qid;
        this.items[qid] ||= {'qid': qid};
        if (this.items[qid].wikidata) return;
        this.items[qid].wikidata = item;
        var group = this.items[qid].group ||= L.featureGroup();

        var icon = blueMarker;
        var label = `${item.label} (${item.qid})`;
        item.markers.forEach((marker_data) => {
          var marker = L.marker(marker_data, { opacity: 0.9, icon: icon });
          marker.addTo(group);
          this.mouse_events(marker, qid);
          marker_data.marker = marker;
        });
        // group.addTo(this.map);
      });

    },

    clear_items() {

      for (const qid of Object.keys(this.items)) {
        this.items[qid].group.removeFrom(this.map);
      }

      this.items = {};
      this.isa_list = [];
      this.isa_ticked = [];
      this.isa_labels = {};
      this.isa_lookup = {};
    },

    load_wikidata_items() {
      this.load_button_pressed = true;
      this.wikidata_loaded = false;
      this.osm_loaded = false;
      this.check_for_missing_done = false;

      this.clear_items();
      this.close_item();

      this.wikidata_loading = true;
      this.osm_loading = true;

      var bounds = this.map.getBounds();

      var items_url = this.api_base_url + "/api/1/items";
      var osm_objects_url = this.api_base_url + "/api/1/osm";

      var params = { bounds: bounds.toBBoxString() };

      axios.get(items_url, { params: params }).then((response) => {
        this.isa_list = response.data.isa_count;
        this.isa_list.forEach(isa => {
          this.isa_ticked.push(isa.qid);
          this.isa_labels[isa.qid] = isa.label;
          this.isa_lookup[isa.qid] = isa;
        });
        this.process_wikidata_items(response.data.items);
        this.wikidata_loaded = true;
        this.wikidata_loading = false;

        this.check_for_missing();
        this.hits = [];
      });

      axios.get(osm_objects_url, { params: params }).then((response) => {
        response.data.objects.forEach((osm) => {
          var qid = osm.wikidata;
          this.items[qid] ||= {'qid': qid};
          this.items[qid].osm ||= [];
          this.items[qid].osm.push(osm);
          var group = this.items[qid].group ||= L.featureGroup();
          var icon = osmYellowMarker;
          var marker = L.marker(osm.centroid, { opacity: 0.9, title: osm.name, icon: icon });
          osm.marker = marker;
          marker.addTo(group);
          this.mouse_events(marker, qid);

          if (osm.type != "node" && osm.geojson) {
            var mapStyle = { fillOpacity: 0 };
            var geojson = L.geoJSON(null, { style: mapStyle });
            geojson.addData(osm.geojson);
            geojson.addTo(group);
            this.items[qid].outline = geojson;
          }
        });
        this.osm_loaded = true;
        this.osm_loading = false;

        this.check_for_missing();
        this.hits = [];
      });
    },
    auto_load() {
      var count_url = this.api_base_url + "/api/1/count";
      var bounds = this.map.getBounds();
      var params = { bounds: bounds.toBBoxString() };
      axios.get(count_url, { params: params }).then((response) => {
        var count = response.data.count;
        if (count < 1000) {
          this.load_wikidata_items();
        }

      });
    },
    run_search() {
      if (!this.search_text) return;
      var params = { q: this.search_text };
      var search_url = this.api_base_url + "/api/1/search";
      axios.get(search_url, { params: params }).then((response) => {
        this.hits = response.data.hits;
      });

    },
    check_for_missing() {
      if (this.check_for_missing_done) return;
      if (!this.osm_loaded || !this.wikidata_loaded) return;

      var missing_qids = [];
      for (const [qid, item] of Object.entries(this.items)) {
        if (!item.wikidata) missing_qids.push(qid);
      }

      console.log('missing:', missing_qids);
      if (missing_qids.length == 0) {
        this.update_wikidata();
        this.check_for_missing_done = true;
        this.start_item();
        return;
      }

      var c = this.map.getCenter();
      var params = {
        qids: missing_qids.join(","),
        lat: c.lat.toFixed(5),
        lon: c.lng.toFixed(5),
      };
      var missing_url = this.api_base_url + "/api/1/missing";
      axios.get(missing_url, { params: params }).then((response) => {
        response.data.isa_count.forEach((isa) => {
          this.isa_labels[isa.qid] = isa.label;
          if (this.isa_lookup[isa.qid] === undefined) {
            this.isa_lookup[isa.qid] = isa;
            this.isa_list.push(isa);
            this.isa_ticked.push(isa.qid);
          } else {
            this.isa_lookup[isa.qid].count += 1;
          }
        });

        this.process_wikidata_items(response.data.items);
        this.update_wikidata();
        this.check_for_missing_done = true;
        this.start_item();
      });
    },
    start_item() {
      if (!this.detail_qid) return;
      this.open_item(this.detail_qid);
      this.detail_qid = undefined;
    },
    update_wikidata() {
      for (const qid in this.items) {
        var item = this.items[qid];
        if (!item.osm) continue

        var wd_item = item.wikidata;

        item.osm.forEach((osm) => {
          osm.marker.setIcon(wd_item ? osmYellowMarker : osmOrangeMarker);
        });

        if (!wd_item) continue;

        wd_item.markers.forEach((marker_data) => {
          marker_data.marker.setIcon(greenMarker);
          item.lines ||= [];
          item.osm.forEach((osm) => {
            var path = [osm.centroid, marker_data];
            var polyline = L.polyline(path, { color: "green" });
            polyline.addTo(item.group)
            this.items[qid].lines.push(polyline);
          });
        });
      }

      for (const qid in this.items) {
        var item = this.items[qid];
        if (item.osm) continue;
        item.wikidata.markers.forEach((marker_data) => {
          marker_data.marker.setIcon(redMarker);
        });
      }
    }
  },
  created() {
    var lat = this.startLat ?? 52.19679;
    var lon = this.startLon ?? 0.15224;
    this.center = [lat, lon];
    this.zoom = this.startZoom || 16;
  },
  mounted() {
    this.$nextTick(function () {
      var options = {
        center: this.center,
        zoom: this.zoom,
      };

      var map = L.map("map", options);
      var osm_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
      var tile_url = "https://tile-c.openstreetmap.fr/hot/{z}/{x}/{y}.png";
      var osm = L.tileLayer(osm_url, {
        maxZoom: 19,
      });
      osm.addTo(map);

      map.on("moveend", this.update_map_path);
      this.map = map;

      this.detail_qid = this.qid_from_url();
      if (this.detail_qid) {
        this.load_wikidata_items();
      } else {
        this.auto_load();
      }
    });

  },
};
</script>

<style>

#nav {
  left: 35%;
  width: 65%;
}

#map {
  position: absolute;
  top: 57px;
  bottom: 0px;
  left: 35%;
  width: 65%;
  z-index: -1;
}

#load-btn {
  position: absolute;
  top: 77px;
  left: 67.5%;
  transform: translate(-50%, 0);
}

#edit-count {
  position: absolute;
  top: 77px;
  right: 80px;
  background: white;
}

#search {
  position: absolute;
  overflow: auto;
  top: 77px;
  left: 20px;
  bottom: 20px;
  width: 25%;
  background: lightgray;
}

.bg-highlight {
  background: lightgray !important;
}

#sidebar {
  position: absolute;
  background: #eee;
  top: 0px;
  left: 0px;
  bottom: 0px;
  overflow: auto;
  width: 35%;
}

</style>
