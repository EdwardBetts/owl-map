<template>
<div>

  <div class="modal fade" ref="error_modal" tabindex="-1">
    <div class="modal-dialog modal-dialog-scrollable modal-xl">
      <div class="modal-content">
        <div class="modal-header bg-danger text-white">
          <h5 class="modal-title">
            <span v-if="api_call_error_message">{{ api_call_error_message }}</span>
            <span v-else>Error from server</span>
          </h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <div v-if="api_call_error_traceback">
            <div>error message: {{ api_call_error_message }}</div>
            <div class="mt-2"><pre>{{ api_call_error_traceback }}</pre></div>
          </div>
        </div>
        <div class="modal-footer bg-danger">
          <button type="button" class="btn btn-primary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>

  <div id="map">
  </div>

  <button ref="btn" id="select-area-btn" type="button" class="btn btn-primary btn-lg" v-if="current_hit" @click.stop="select_area()">
    Select this area
  </button>


  <div class="alert alert-primary alert-map" role="alert" v-if="area_too_big">
    Zoom in to see Wikidata items on the map.
  </div>

  <div class="alert alert-primary alert-map" role="alert" v-if="loading">
    Found {{ item_count }} Wikidata items. Updating markers. <span class="spinner-border spinner-border-sm"></span>
  </div>

  <div class="alert alert-primary alert-map text-center" role="alert" v-if="!area_too_big && this.too_many_items">
    Found {{ this.item_count.toLocaleString('en-US') }} Wikidata items.<br/> Zoom in to see them.
  </div>

  <div id="edit-count" class="p-2" v-if="!upload_state && edits.length">
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
        <button :disabled="upload_state !== undefined && upload_state != 'done'"
           type="button"
           class="btn-close float-end"
           @click="close_edit_list"></button>
      </div>

      <div class="card w-100 bg-light mb-2">
        <div class="card-body">

          <template v-if="upload_state === undefined">
            <div v-if="mockUpload" class="alert alert-danger">
              <i class="fa fa-exclamation-triangle"></i>
              Changes won't be saved to OpenStreetMap. This software uses a mock upload process to allow testing of the user interface, while it is still in development.
            </div>
            <div v-else class="alert alert-info">
              <i class="fa fa-info-circle"></i>
              Editing is live, changes will be uploaded to OpenStreetMap.
            </div>
          </template>

          <p class="card-text">
            {{ edits.length + (edits.length == 1 ? " edit" : " edits") }} to upload
          </p>
          <form @submit.prevent="upload">
            <div class="mb-3">
              <label for="changesetComment" class="form-label">Changeset comment</label>
              <input
                :disabled="upload_state !== undefined"
                type="text"
                class="form-control"
                id="changesetComment"
                v-model="changeset_comment">
            </div>
            <button
              :disabled="changeset_comment && upload_state !== undefined"
              type="submit"
              class="btn btn-primary">
              <i class="fa fa-upload"></i> Save to OpenStreetMap
            </button>
          </form>

          <div class="progress mt-2">
            <div :style="{ width: upload_progress + '%' }"
                 class="progress-bar"
                 role="progressbar"></div>
          </div>


        </div>
      </div>

      <div v-if="upload_state == 'auth-fail'" class="alert alert-danger" role="alert">
        <p>The OpenStreetMap returned an error: "Couldn't authenticate you".</p>
        <p>To workaround this error you need to logout and login again.</p>
      </div>

      <div v-if="upload_state == 'init'" class="alert alert-info" role="alert">
        <i class="fa fa-info-circle"></i>
        Starting upload.
      </div>

      <div v-if="upload_state == 'uploading'" class="alert alert-info" role="alert">
        <i class="fa fa-info-circle"></i>
        Uploading changes.
      </div>

      <div v-if="upload_state == 'closing'" class="alert alert-info" role="alert">
        <i class="fa fa-info-circle"></i>
        Closing changeset.
      </div>

      <div v-if="upload_state == 'done'" class="alert alert-success" role="alert">
        <i class="fa fa-info-circle"></i>
        Changes saved.
        <a :href="`https://www.openstreetmap.org/changeset/${changeset_id}`"
          target="_blank">
          view your changeset <i class="fa fa-external-link"></i>
        </a>
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
                    <td class="text-end">
                      <span class="text-nowrap">{{ osm.distance.toFixed(0) }}m</span><br>
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
                        <br>nodes within building: {{ osm.address_list.join("; ") }}
                    </span>

                    <span v-if="osm.part_of">
                        <br>part of:
                        <span v-for="(part_of, part_of_index) in osm.part_of">
                          <span v-if="part_of_index != 0">, </span>
                          {{ part_of.tags.name }}
                        </span>
                    </span>

                    <br>
                      <span v-if="osm.selected">
                        add tag: <span class="badge bg-success">wikidata={{ edit.qid }}</span>
                      </span>
                      <span v-else>
                        remove tag: <span class="badge bg-danger">wikidata={{ edit.qid }}</span>
                      </span>

                      <span v-if="osm.upload_state == 'current'"
                            class="ms-2 badge bg-info">uploading</span>
                      <span v-if="osm.upload_state == 'saved'"
                            class="ms-2 badge bg-success">saved</span>

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

      <div v-if="!edits.length" class="card m-2">
        <div class="card-body">
          <form id="search-form" class="row row-cols-lg-auto g-3 align-items-center" @submit.prevent="run_search">
            <div class="col-12">
              <input class="form-control" id="search-text" v-model.trim="search_text" placeholder="place">
            </div>
            <div class="col-12">
              <button type="submit" id="search-btn" class="btn btn-primary">search</button>

            </div>
          </form>
          <p v-if="recent_search" class="card-text mt-2">Searching for '{{ recent_search }}', found {{ hits.length }} places.</p>
          <div class="list-group" v-if="hits.length">
            <a class="list-group-item list-group-item-action"
                :class="{ active: hit == this.current_hit }"
                v-bind:key="hit.identifier"
                v-for="hit in hits"
                :href="hit_url(hit)"
                @mouseenter="show_hit_on_map(hit)"
                @click.prevent="visit(hit)">
              {{ hit.name }} ({{ hit.label }})
            </a>
          </div>
          <div class="alert alert-info mt-2" v-if="hits.length">
            <i class="fa fa-info-circle"></i>
            <span v-if="hits.length == 1">
              One search result. Click the result to continue.
            </span>
            <span v-else>
              Click a result to continue.
            </span>
          </div>
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" id="type-filter" v-model="show_item_type_filter">
            <label class="form-check-label" for="type-filter">item type filter</label>
          </div>

          <div class="card" v-if="show_item_type_filter">
            <div class="card-body">
              <h5 class="card-title">item type filters</h5>
              <input class="form-control" v-model.trim="item_type_search" placeholder="item type">

              <div class="list-group" v-if="item_type_hits.length">
                <a class="list-group-item"
                    v-bind:key="isa.qid"
                    v-for="isa in item_type_hits"
                    href="#"
                    @click.prevent="item_type_filters.includes(isa) || item_type_filters.push(isa)"
                    >
                  {{ isa.label }} ({{ isa.qid }})
                </a>
              </div>

              <h6>current item type filters</h6>
              <div class="list-group" v-if="item_type_filters.length">
                <a class="list-group-item" v-bind:key="isa.qid" v-for="(isa, index) in item_type_filters" href="#">
                  {{ isa.label }} ({{ isa.qid }})
                  <button type="button"
                      class="btn btn-danger btn-sm"
                      @click="item_type_filters.splice(index, 1)">remove</button>
                </a>
              </div>
              <div v-else>no item type filters</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card m-2" v-if="show_instructions">
        <div class="card-body">
          <div class="h3 card-title">Link Wikidata and OpenStreetMap</div>
          <div class="alert alert-danger">
            <i class="fa fa-exclamation-triangle"></i>
            This software is beta, it works but is incomplete. <a href="/documentation">See what's broken</a>.
            <!-- This software is unfinished. Only mock editing happens, nothing is uploaded to the OpenStreetMap database yet. <a href="/documentation" class="alert-link">See what's broken</a> -->
          </div>

          <p class="card-text">This tool will help you link Wikidata items with the matching object on OpenStreetMap (OSM).</p>

          <p v-if="!username" class="card-text">To save changes you need to <a href="/login">login via OpenStreetMap</a>.</p>

          <p class="card-text">Zoom in or search for an area to work on.</p>

          <hr>

          <p>This project was created by Edward Betts
          [<a href="https://twitter.com/edwardbetts/"><i class="fa fa-twitter"></i></a>].</p>

          <p class="card-text">
            Discussion of collaboration between Wikidata and OpenStreetMap happens on the
            <a href="https://t.me/wikimaps" target="_blank" class="text-nowrap">
              <i class="fa fa-telegram"></i>Wikimaps Telegram channel</a> and the
            <a href="https://osmus.slack.com/archives/CUP8V1Z61" target="_blank" class="text-nowrap">
              <i class="fa fa-slack"></i>OpenStreetMap/Wikimedia Slack channel</a>.
          </p>

          <!--

          <p class="card-text">The map will show at most 400 items, if there are more then you need to zoom in before you can start editing.</p>

          <p class="card-text">Wikidata items appear on the map as red or green markers. Items not linked for OSM appear in red, those that are linked appear in green. The map shows the location of Wikidata tagged OSM objects with a yellow pin.</p>

          <p class="card-text">There are controls to filter what appears on the map. You have the option to hide Wikidata items that are already tagged on OSM. The type filter allows you to adjust what types of Wikidata item are displayed.</p>

          <p class="card-text">Click on a marker to show details of the Wikidata item and find nearby possible OSM matches.</p>
          -->
        </div>
      </div>

      <div class="card m-2" v-if="!view_edits && isa_list.length">
        <div class="card-body">
          <div class="h5 card-title">Map key</div>
          <ui class="list-group">
            <li class="list-group-item">
              <i style="background: #a23337; color: white" class="p-1 fa fa-wikidata"></i>
              Wikidata item without OSM link
            </li>
            <li class="list-group-item">
              <i style="background: #6dae40; color: white" class="p-1 fa fa-wikidata"></i>
              Wikidata item with OSM link
            </li>
            <li class="list-group-item">
              <i style="background: #f5bb39; color: white" class="p-1 fa fa-map"></i>
              Linked OSM object
            </li>
          </ui>
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
          <div>
            <button type="button" class="btn btn-primary btn-sm m-1" @click.prevent="isa_tick_all">select all</button>
            <button type="button" class="btn btn-primary btn-sm m-1" @click.prevent="isa_ticked=[]">clear selection</button>
          </div>

          <div class="list-group" @mouseout="this.hover_isa=undefined">
            <label class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" v-for="isa in isa_list" @mouseenter="this.hover_isa=isa">
              <span>
              <input class="form-check-input me-1" type="checkbox" :id="'isa-' + isa.qid" :value="isa.qid" v-model="isa_ticked">
              {{ isa.label }} ({{ isa.qid }})
              <a href="#" @click.prevent="isa_ticked=[isa.qid]">only</a>
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

          <button class="btn btn-primary btn-sm ms-2" @click="zoom_to_selected_marker()">
            <i class="fa fa-search-plus"></i> zoom in on item
          </button>

          <button type="button" class="btn-close float-end" id="close-detail" @click="close_item()"></button>
        </div>
        <div id="detail">
          <div class="row"><div class="col-xl-6">

          <strong>Wikidata item</strong><br>
          <a :href="qid_url(wd_item.qid)" target="_blank">{{ wd_item.label }}</a> ({{ wd_item.qid }})

          <span v-if="wd_item.description">
            <br><strong>description</strong><br>{{ wd_item.description }}
          </span>

          <span v-if="wd_item.aliases !== undefined && wd_item.aliases.length">
            <br><strong>aliases</strong>
            <br>{{ wd_item.aliases.join("; ") }}
          </span>

          <br><strong>item type</strong>
          <span v-bind:key="`isa-${wd_item.qid}-${isa_qid}`" v-for="isa_qid in wd_item.isa_list">
            <br><a :href="qid_url(isa_qid)" target="_blank">{{isa_labels[isa_qid]}}</a> ({{isa_qid}})
          </span>

          <span v-if="wd_item.street_address.length">
            <br><strong>street address</strong>
            <br>{{wd_item.street_address[0]}}
          </span>

          <span v-if="wd_item.closed.length">
            <br><strong>closed</strong>
            <br>{{wd_item.closed.join('; ')}}
          </span>

          <span v-if="wd_item.heritage_designation.length">
            <br><strong>heritage designation</strong>
            <br>{{ wd_item.heritage_designation.join("; ") }}
          </span>

          </div>

          <div class="col-xl-6">

          <div v-if="bounds_before_open" class="alert alert-info">
            <i class="fa fa-info-circle"></i> Close item to zoom out.
          </div>

          <div v-if="current_item.tag_or_key_list && current_item.tag_or_key_list.length">
            <strong>OSM tags/keys to search for</strong><br/>
            {{ current_item.tag_or_key_list.length }} tags/keys to consider
            <a href="#" @click.prevent="show_tag_or_key_list = !show_tag_or_key_list">show/hide</a><br/>
            <div v-if="show_tag_or_key_list">
              <div v-for="v in current_item.tag_or_key_list">{{ v }}</div>
            </div>
          </div>


          <span v-if="wd_item.image_list.length">
            <strong>Image from Wikidata</strong><br/>
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

        <div class="form-check form-switch">
          <input class="form-check-input" type="checkbox" id="debug" v-model="debug">
          <label class="form-check-label" for="debug">debug</label>
        </div>

        <div v-if="debug">
          API calls:
          <a :href="`${api_base_url}/api/1/count?${bounds_param()}`" target="_blank">count</a> |
          <a :href="`${api_base_url}/api/1/isa?${bounds_param()}`" target="_blank">item type counts</a> |
          <a :href="`${api_base_url}/api/1/item/${wd_item.qid}`" target="_blank">item detail</a> |
          <a :href="`${api_base_url}/api/1/item/${wd_item.qid}/tags`" target="_blank">item tags</a> |
          <a :href="`${api_base_url}/api/1/item/${wd_item.qid}/candidates`" target="_blank">nearby OSM candidates</a>
        </div>

        <div v-if="!current_item.nearby" class="alert alert-info">
          Searching for nearby OSM matches <span class="spinner-border spinner-border-sm"></span>
        </div>

        <div v-if="current_item.nearby && !current_item.nearby.length">
          <strong>No OSM matches found nearby</strong>
        </div>
        <div v-if="current_item.nearby && current_item.nearby.length">

          <div v-if="!username" class="alert alert-info">
            <i class="fa fa-info-circle"></i>
            <a href="/login">Login with OpenStreetMap</a> to add Wikidata tags</div>

          <div v-if="edits.length" class="alert alert-info">
            <i class="fa fa-info-circle"></i>
            Use the save button in the top right corner of the map to upload changes.
          </div>

          <strong>Possible OSM matches</strong> (sorted by distance from item)<br>
          show:
          <div class="form-check form-switch form-check-inline">
            <input class="form-check-input" type="checkbox" id="show-tags" v-model="show_tags">
            <label class="form-check-label" for="show-tags">tags</label>
          </div>
          <div class="form-check form-switch form-check-inline">
            <input class="form-check-input" type="checkbox" id="show-area" v-model="show_area">
            <label class="form-check-label" for="show-area">area</label>
          </div>
          <div class="form-check form-switch form-check-inline">
            <input class="form-check-input" type="checkbox" id="show-presets" v-model="show_presets">
            <label class="form-check-label" for="show-presets">type</label>
          </div>

          <table class="table table-sm table-hover" @mouseleave="this.current_osm = undefined">
            <tbody>
              <tr
                  v-for="osm in current_item.nearby"
                  class="osm-candidate"
                  :class="{ 'table-success': osm.selected }"
                  @mouseenter="this.current_osm=osm"
                  @click="select_osm(current_item, osm)">
                <td class="text-nowrap">
                  <input class="form-check-input" type="checkbox" v-model="osm.selected" v-if="username" />
                  {{ osm.distance.toFixed(0) }}m
                  <a
                    :href="'https://www.openstreetmap.org/' + osm.identifier"
                    target="_blank"
                    @click.stop><i class="fa fa-map-o"></i></a>
                </td>
                <td>
                <span class="badge bg-primary float-end">{{ osm.type }}</span>
                <span v-if="osm.name">{{ osm.name }} </span>
                <i v-else>no name </i>
                <template v-if="show_presets && osm.presets.length">
                  <br>
                <span v-for="(p, index) in osm.presets">
                  <span v-if="index != 0">, </span>
                  <a
                    :href="'http://wiki.openstreetmap.org/wiki/' + p.tag_or_key"
                    class="osm-wiki-link"
                    target="_blank"
                    @click.stop>{{p.name}} <i class="fa fa-external-link"></i></a>
                </span>
                </template>

                <span v-if="osm.address && osm.address != osm.name">
                    <br>street address: {{ osm.address }}
                </span>
                <span v-else-if="osm.tags['addr:street'] && osm.address != osm.name">
                    <br>street: {{ osm.tags['addr:street'] }}
                </span>

                <span v-if="osm.address_list.length">
                    <br>nodes within building: {{ osm.address_list.join("; ") }}
                </span>

                <span v-if="osm.part_of">
                    <br>part of:
                    <span v-for="(part_of, part_of_index) in osm.part_of">
                      <span v-if="part_of_index != 0">, </span>

                    <a
                      :href="`https://www.openstreetmap.org/${part_of.type}/${part_of.id}`"
                      target="_blank"
                      @click.stop>
                      {{ part_of.tags.name }} <i class="fa fa-map-o"></i></a>
                    </span>

                </span>

                <span v-if="osm.tags.ele">
                    <br>elevation: {{ osm.tags.ele }} m
                </span>

                <span v-if="show_area && osm.area && osm.area > 10 * 10">
                    <br>area: {{ format_area(osm.area) }}
                </span>

                <span v-if="osm.tags.wikidata">
                  <br>Wikidata tag:
                  <a :href="`https://wikidata.org/wiki/${osm.tags.wikidata}`">{{ osm.tags.wikidata }}</a>
                  <span class="ms-1">
                    <span v-if="osm.tags.wikidata == wd_item.qid" class="badge bg-success">this item</span>
                    <span v-else class="badge bg-info">different item</span>
                  </span>
                </span>
                <div class="card" v-if="show_tags">
                  <div class="card-body tag-card-body">
                    <span class="badge bg-secondary float-end">tags</span>
                 <div class="card-text" v-for="(value, key) of osm.tags">
                   <strong>{{ key }}</strong>:
                     {{ value.replace(/;/g, '; ') }}
                   </div>
                </div>
                </div>
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
import {unref, toRaw} from 'vue';

var redMarker = ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "red",
  shape: "circle",
  prefix: "fa",
});

var greenMarker = ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "green-light",
  shape: "circle",
  prefix: "fa",
});

var greenDarkMarker = ExtraMarkers.icon({
  icon: "fa-wikidata",
  markerColor: "green-dark",
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

var osmOrangeMarker = ExtraMarkers.icon({
  icon: "fa-map",
  markerColor: "orange",
  shape: "square",
  prefix: "fa",
});

function beforeUnloadListener(event) {
    event.preventDefault();
    return event.returnValue = "";
};

export default {
  props: {
    startLat: Number,
    startLon: Number,
    startZoom: Number,
    startRadius: Number,
    username: String,
    startMode: String,
    q: String,
    defaultComment: String,
    mockUpload: Boolean,
  },
  data() {
    return {
      api_base_url: "https://v2.osm.wikidata.link",
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
      changeset_comment: undefined,
      changeset_id: undefined,
      upload_state: undefined,
      upload_progress: 0,
      show_tags: false,
      show_area: true,
      show_presets: true,
      flag_show_hover_isa: false,
      debug: false,
      map_area: undefined,
      item_count: undefined,
      mode: undefined,
      current_hit: undefined,
      recent_search: undefined,
      show_item_type_filter: false,
      item_type_search: undefined,
      item_type_hits: [],
      item_type_filters: [],
      bounds_before_open: undefined,
      bounds_done: [],
      zoom_on_open: false,
      selected_marker: undefined,
      debug_info: [],
      map_update_number: 0,
      api_call_error_message: undefined,
      api_call_error_traceback: undefined,
    };
  },
  computed: {
    show_instructions() {
      return (this.mode != "search"
              && !this.loading
              && !this.isa_list.length
              && !this.view_edits
              && !this.current_item);
    },
    area_too_big() {
      return !this.item_type_filters.length && this.map_area > 1000 * 1000 * 1000;
    },
    too_many_items() {
      return this.item_count > 600;
    },
    loading() {
      return this.osm_loading || this.wikidata_loading;
    },
    current_qid() {
      return this.current_item ? this.current_item.wikidata.qid : undefined;
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
    item_is_selceted(item) {
      return item.wikidata.isa_list.some(isa => this.isa_ticked.includes(isa));
    },
    selected_items() {
      var ret = {};
      for (const qid in this.items) {
        if (!this.items[qid]) continue;
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
    edits(edit_list) {
      this.update_unload_warning(edit_list);
    },
    item_type_search(value) {
      if (value.length < 3) {
        this.item_type_hits = [];
        return;
      }

      var params = { q: value };
      var isa_search_url = `${this.api_base_url}/api/1/isa_search`;

      axios.get(isa_search_url, { params: params }).then((response) => {
        this.item_type_hits = response.data.items;
      });
    },
    selected_items(new_items, old_items) {
      for (const qid of Object.keys(new_items)) {
        if (!old_items[qid])
          new_items[qid].group.addTo(this.map);
      }

      for (const qid of Object.keys(old_items)) {
        if (!new_items[qid])
          old_items[qid].group.removeFrom(this.map);
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
        var circle = L.circleMarker(coords, { radius: 20, color: "orange" }).addTo(this.map);
        this.selected_circles.push(circle);
      });

    },
    hover_isa(highlight_isa) {
      // if (!this.flag_show_hover_isa) return;
      this.drop_hover_circles();

      for(const item of Object.values(this.selected_items)) {
        // var opacity = 0.9;
        if (highlight_isa) {
          var match = item.wikidata.isa_list.some(isa => isa == highlight_isa.qid);
          // opacity = match ? 1 : 0.2;
          if (match) {
            this.add_hover_circles(item);
          }
        }
        // this.set_item_opacity(item, opacity);

      }
    }
  },
  methods: {
		api_call(endpoint, options) {
      var url = `${this.api_base_url}/api/1/${endpoint}`;
			return axios.get(url, options).catch(this.show_api_error_modal);
		},
    update_unload_warning(edit_list) {
      if (edit_list.length) {
        addEventListener("beforeunload", beforeUnloadListener, {capture: true});
      } else {
        removeEventListener("beforeunload", beforeUnloadListener, {capture: true});
      }
    },
    format_area(area) {
      var value, unit, dp;
      if(area > 1000 * 1000) {
        value = area / (1000 * 1000);
        unit = "km²";
        dp = 1;
      } else {
        value = area;
        unit = "m²";
        dp = 0;
      }

      return value.toLocaleString("en-US", {maximumFractionDigits: dp}) + " " + unit
    },
    bounds_area(bounds) {
      var width = bounds.getSouthWest().distanceTo(bounds.getSouthEast());
      var height = bounds.getSouthWest().distanceTo(bounds.getNorthWest());

      return width * height;
    },
    bounds_param() {
      return 'bounds=' + this.map.getBounds().toBBoxString();
    },
    show_api_error_modal(error) {
      var reply = error.data;
      this.api_call_error_message = reply.error;
      this.api_call_error_traceback = reply.traceback;
      var error_modal = new bootstrap.Modal(this.$refs.error_modal);

      this.$refs.error_modal.addEventListener('hidden.bs.modal', function (event) {
        this.api_call_error_message = undefined;
        this.api_call_error_traceback = undefined;
      })

      error_modal.show();
    },
    test_api_error() {
      this.api_call("error");
    },
    close_edit_list() {
      this.view_edits = false;
      if (this.upload_state != 'done') return;

      this.edits.forEach(edit => {
        var item = edit.item;
        var identifier = edit.osm.identifier;
        edit.outline.removeFrom(this.map);
        if (edit.osm.selected) {
          if (item.osm) {
            if (item.osm[identifier]) return;
          } else {
            item.osm = {};
          }

          var keys = ['identifier', 'id', 'type', 'geojson', 'centroid', 'name'];
          var osm = Object.fromEntries(keys.map(key => [key, edit.osm[key]]));
          osm['wikidata'] = item.qid;
          item.osm[identifier] = osm;
          this.add_osm_to_map(item, osm);

          item.lines ||= [];
          item.wikidata.markers.forEach((marker_data) => {
            var path = [osm.centroid, marker_data];
            var polyline = L.polyline(path, { color: "green" });
            polyline.addTo(item.group);
            item.lines.push(polyline);
          });
        }
      });

      var updated_items = new Set(this.edits.map(edit => edit.item));
      this.edits = [];
      this.upload_progress = 0;
      this.upload_state = undefined;

      updated_items.forEach(item => {
        var marker = this.getMarker(item);

        item.wikidata.markers.forEach((marker_data) => {
          marker_data.marker.setIcon(marker);
        });
      });
    },
    upload() {
      console.log('upload triggered');
      this.upload_state = "init";
      var edit_list = [];
      this.edits.forEach((edit) => {
        var e = {
          'qid': edit.item.qid,
          'osm': edit.osm.identifier,
          'op': (edit.osm.selected ? 'add' : 'remove'),
        };
        edit_list.push(e);
      });
      var post_json = {
        'comment': this.changeset_comment,
        'edit_list': edit_list,
      }
      console.log('post new session');
      var edit_session_url = `${this.api_base_url}/api/1/edit`;
      axios.post(edit_session_url, post_json).then((response) => {
        var session_id = response.data.session_id;
        var save_url = `${this.api_base_url}/api/1/save/${session_id}`;
        console.log('new event source');
        const es = new EventSource(save_url);
        es.onerror = function(event) {
          console.log('event source:', es);
          console.log('ready state:', es.readyState);
        }
        var app = this;
        es.onmessage = function(event) {
          const data = JSON.parse(event.data);
          switch(data.type) {
            case "auth-fail":
              app.upload_state = "auth-fail";
              console.log("auth-fail");
              es.close();
              break;
            case "changeset-error":
              app.upload_state = "changeset-error";
              app.upload_error = data.error;
              console.log("changeset-error", data.error);
              es.close();
              break;
            case "open":
              app.upload_state = "uploading";
              app.changeset_id = data.id;
              break;
            case "progress":
              var edit = app.edits[data.num];
              app.upload_progress = ((data.num + 1) * 100) / app.edits.length;
              edit.osm.upload_state = "progress";
              break;
            case "saved":
              var edit = app.edits[data.num];
              edit.osm.upload_state = "saved";
              break;
            case "closing":
              app.upload_state = "closing";
              break;
            case "done":
              app.upload_state = "done";
              removeEventListener("beforeunload", beforeUnloadListener, {capture: true});
              es.close();
              break;
          }
          console.log('upload state:', app.upload_state);
        }
      });
    },
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
      if (!this.username) return;
      osm.selected = !osm.selected;
      var index = this.edit_list_index(item, osm);

      if (index == -1) {
        var mapStyle = { fillOpacity: 0, color: "darkturquoise" };
        var geojson = L.geoJSON(null, { style: mapStyle });
        geojson.addData(osm.geojson);
        geojson.addTo(this.map);

        this.edits.push({'item': item, 'osm': osm, 'outline': geojson});

      } else {
        var edit = this.edits[index];
        edit.outline.removeFrom(this.map);
        this.edits.splice(index, 1);
      }

      this.update_unload_warning(this.edits);

      var marker = this.getMarker(item);

      item.wikidata.markers.forEach((marker_data) => {
        marker_data.marker.setIcon(marker);
      });


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
        path += `?item=${this.current_qid}`;
      }
      return path;
    },

    mouse_events(marker, qid) {
      marker.on("mouseover", () => { this.add_highlight(qid); });
      marker.on("mouseout", () => { this.drop_highlight(qid); });
      marker.on("click", () => { this.open_item(qid, marker); });

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
        var circle = L.circleMarker(coords, { radius: 20 }).addTo(this.map);
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
    map_moved() {
      if (this.mode == "search") return;
      this.auto_load();
      this.update_map_path();
    },
    current_state() {
      var c = this.map.getCenter();
      return {
        mode: this.mode,
        zoom: this.map.getZoom(),
        lat: c.lat.toFixed(5),
        lon: c.lng.toFixed(5),
        search_text: this.search_text,
        detail_qid: this.current_qid,
        item_count: this.item_count,
        map_area: this.map_area,
        hits: toRaw(this.hits),
        current_hit: toRaw(this.current_hit),
        current_osm: toRaw(this.current_osm),
        recent_search: this.recent_search,
      };
    },
    update_map_path() {
      var state = this.current_state();
      history.replaceState(state, '', this.build_map_path());
    },
    open_item(qid, marker) {
      this.close_edit_list();

      var item = this.items[qid];
      if (marker) {
        this.selected_marker = marker;
      } else {
        marker = item.markers[0].marker;
        this.selected_marker = undefined;
      }

      if (this.current_item == item) return; // already open
      this.current_osm = undefined;
      this.current_item = item;

      var state = this.current_state();
      history.pushState(state, '', this.build_map_path());

      this.hover_isa = undefined;

      if (item.detail_requested !== undefined) return;
      item.detail_requested = true;

      this.api_call(`item/${qid}/tags`).then((response) => {
        var qid = response.data.qid;
        this.items[qid].tag_or_key_list = response.data.tag_or_key_list;
        this.items[qid].tag_src = response.data.tag_src;
      });

      this.api_call(`item/${qid}/candidates`).then((response) => {
        var qid = response.data.qid;
        var item = this.items[qid];
        var osm_identifiers = item.osm ? Object.keys(item.osm) : [];

        item.nearby = response.data.nearby;
        item.nearby.forEach((osm) => {
          osm.selected = osm_identifiers.includes(osm.identifier);
          if (this.edits.length && this.edit_list_index(item, osm) != -1) {
            osm.selected = !osm.selected;
          }
        });

        if (response.data.nearby.length) {
          if (this.zoom_on_open) {
            if (!this.bounds_before_open) {
              this.bounds_before_open = this.map.getBounds();
            }
            this.map.flyTo(marker.getLatLng(), 18);
          }
        }

      });
    },
    zoom_to_selected_marker() {
      var marker = this.selected_marker || this.current_item.markers[0];
      if (!this.bounds_before_open) {
        this.bounds_before_open = this.map.getBounds();
      }
      this.map.flyTo(marker.getLatLng(), 18);
    },
    item_has_edit(item) {
      if (this.edits.length == 0) return false;
      return this.edits.some((edit) => edit.item.qid == item.qid);
    },
    close_item() {
      this.current_osm = undefined;
      this.current_item = undefined;
      this.selected_marker = undefined;
      this.update_map_path();
      if (this.bounds_before_open) {
        this.map.flyToBounds(this.bounds_before_open);
        this.bounds_before_open = undefined;
      }
    },
    qid_url(qid) {
      return "https://www.wikidata.org/wiki/" + qid;
    },
    getMarker(item) {
      if (!this.osm_loaded) return blueMarker;
      if (this.item_has_edit(item)) {
        return greenDarkMarker;
      } else {
        return item.osm ? greenMarker : redMarker;
      }
    },
    hit_url(hit) {
      var lat = parseFloat(hit.lat).toFixed(5);
      var lon = parseFloat(hit.lon).toFixed(5);
      return `/map/16/${lat}/${lon}`
    },
    fit_bounds_to_hit(hit) {
      var bounds = [[hit.boundingbox[0], hit.boundingbox[2]],
                    [hit.boundingbox[1], hit.boundingbox[3]]];
      this.map.fitBounds(bounds);
    },
    show_hit_on_map(hit) {
      this.fit_bounds_to_hit(hit);
      this.current_hit = hit;
      this.update_search_state();
    },
    select_area() {
      this.current_hit = undefined;
      this.mode = "map";
      this.hits = [];
      this.search_text = "";
      this.auto_load();

      var state = this.current_state();
      history.pushState(state, '', this.build_map_path());
    },

    visit(hit) {
      this.current_hit = undefined;
      this.hits = [];
      this.recent_search = undefined;
      this.search_text = "";
      this.fit_bounds_to_hit(hit);
      this.mode = "map";

      var state = this.current_state();
      history.pushState(state, '', this.build_map_path());

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

    clear_isa() {
      this.isa_list = [];
      // this.isa_ticked = [];
      this.isa_labels = {};
      this.isa_lookup = {};
    },

    clear_items() {
      for (const qid of Object.keys(this.items)) {
        this.items[qid].group.removeFrom(this.map);
      }

      this.items = {};
      this.clear_isa();
    },
    add_osm_to_map(item, osm) {
        var group = item.group ||= L.featureGroup();
        var icon = osmYellowMarker;
        var marker = L.marker(osm.centroid, { opacity: 0.9, title: osm.name, icon: icon });
        osm.marker = marker;
        marker.addTo(group);
        this.mouse_events(marker, item.qid);

        if (osm.type != "node" && osm.geojson) {
          var mapStyle = { fillOpacity: 0 };
          var geojson = L.geoJSON(null, { style: mapStyle });
          geojson.addData(osm.geojson);
          geojson.addTo(group);
          item.outline = geojson;
        }
    },
    load_wikidata_items(bounds) {
      this.load_button_pressed = true;
      this.wikidata_loaded = false;
      this.osm_loaded = false;
      this.check_for_missing_done = false;

      this.wikidata_loading = true;
      this.osm_loading = true;

      var params = { bounds: this.bbox_string(bounds) };

      if (this.item_type_filters.length) {
        params["isa"] = this.item_type_filters.map(isa => isa.qid).join(",");
      }

      this.debug_info.push(`${this_update}: get items ` + this.bbox_string(bounds));
      this.api_call("items", { params: params }).then((response) => {
        if (this.map_update_number > this_update) {
          this.debug_info.push(`${this_update}: got items, took ${response.data.duration.toFixed(4)} seconds. ignoring, ${this.map_update_number} is newer`)
          return;
        }
        this.clear_isa();
        this.isa_list = response.data.isa_count;
        this.isa_list.forEach(isa => {
          this.isa_ticked.push(isa.qid);
          /* if (this.detail_qid || this.item_type_filters.length) {
            this.isa_ticked.push(isa.qid);
          } */
          this.isa_labels[isa.qid] = isa.label;
          this.isa_lookup[isa.qid] = isa;
        });
        this.debug_info.push(`${this_update} got items, took ${response.data.duration.toFixed(4)} seconds`)
        this.process_wikidata_items(response.data.items);
        this.wikidata_loaded = true;

        this.check_for_missing();
        this.hits = [];

        this.wikidata_loading = false;
      });

      this.debug_info.push(`${this_update}: get OSM objects ` + this.bbox_string(bounds));
      this.api_call("osm", { params: params }).then((response) => {
        var osm_count = response.data.objects.length;

        if (this.map_update_number > this_update) {
          this.debug_info.push(`${this_update}: got OSM: ${osm_count} objects. took ${response.data.duration.toFixed(4)} seconds, ignoring, ${this.map_update_number} is newer`)
          return;
        }

        this.debug_info.push(`${this_update}: got OSM: ${osm_count} objects. took ${response.data.duration.toFixed(4)} seconds`)
        response.data.objects.forEach((osm) => {
          var qid = osm.wikidata;
          var item = this.items[qid] ||= {'qid': qid};
          if (item.osm) {
            if (item.osm[osm.identifier]) return;
          } else {
            item.osm = {};
          }
          item.osm[osm.identifier] = osm;
          this.add_osm_to_map(item, osm);

        });
        this.osm_loaded = true;

        this.check_for_missing();
        this.hits = [];

        this.osm_loading = false;
      });
    },
    bbox_string(bounds) {
      const dp = 4;
      return [bounds.getWest().toFixed(dp),
              bounds.getSouth().toFixed(dp),
              bounds.getEast().toFixed(dp),
              bounds.getNorth().toFixed(dp)].join(',');
    },
    auto_load(bounds) {
      bounds ||= this.map.getBounds();
      this.map_area = this.bounds_area(bounds);
      if (this.area_too_big) {
        this.item_count = undefined;
        if (this.items) this.clear_items();
        return;
      }
      var params = { bounds: this.bbox_string(bounds) };

      if (this.item_type_filters.length) {
        params["isa"] = this.item_type_filters.map(isa => isa.qid).join(",");
        console.log(params.isa);
      }

      this.debug_info.push("count " + this.bbox_string(bounds));
      this.api_call("count", { params: params }).then((response) => {
        this.item_count = response.data.count;
        this.debug_info.push(`item count: ${this.item_count}, took ${response.data.duration.toFixed(4)} seconds`)
        if (!this.too_many_items) this.load_wikidata_items(bounds);
      });
    },
    update_search_state() {
      history.replaceState(this.current_state(), '', "/search?q=" + this.search_text);
    },
    search_path() {
        return "/search?q=" + this.search_text;
    },
    run_search() {
      if (!this.search_text) return;
      this.current_hit = undefined;
      var params = { q: this.search_text };
      this.api_call("search", { params: params }).then((response) => {
        this.hits = response.data.hits;
        if (!this.hits.length) return;

        this.recent_search = this.search_text;
        this.item_count = undefined;
        this.map_area = undefined;
        this.clear_items();
        this.mode = "search";

        this.current_hit = this.hits[0];
        this.fit_bounds_to_hit(this.current_hit);
        history.pushState(this.current_state(), '', this.search_path());
      });

    },
    check_for_missing() {
      if (this.check_for_missing_done) return;
      if (!this.osm_loaded || !this.wikidata_loaded) return;

      var missing_qids = [];
      for (const [qid, item] of Object.entries(this.items)) {
        if (!item.wikidata) missing_qids.push(qid);
      }

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
      this.debug_info.push("missing: " + params.qids);
      this.api_call("missing", { params: params }).then((response) => {
        var item_count = response.data.items.length;
        this.debug_info.push(`missing done: ${item_count} items, took ${response.data.duration.toFixed(2)} seconds`);
        response.data.isa_count.forEach((isa) => {
          this.isa_labels[isa.qid] = isa.label;
          if (this.isa_lookup[isa.qid] === undefined) {
            this.isa_lookup[isa.qid] = isa;
            this.isa_list.push(isa);
            this.isa_ticked.push(isa.qid);
            /* if (this.detail_qid || this.item_type_filters.length) {
              this.isa_ticked.push(isa.qid);
            } */
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
      this.open_item(this.detail_qid, null);
      this.detail_qid = undefined;
    },
    update_wikidata() {
      for (const qid in this.items) {
        var item = this.items[qid];
        if (!item.osm) continue

        var wd_item = item.wikidata;

        Object.values(item.osm).forEach((osm) => {
          osm.marker.setIcon(wd_item ? osmYellowMarker : osmOrangeMarker);
        });

        if (!wd_item) continue;

        wd_item.markers.forEach((marker_data) => {
          var marker = this.item_has_edit(item) ? greenDarkMarker : greenMarker;
          marker_data.marker.setIcon(marker);
          item.lines ||= [];
          Object.values(item.osm).forEach((osm) => {
            var path = [osm.centroid, marker_data];
            var polyline = L.polyline(path, { color: "green" });
            polyline.addTo(item.group);
            item.lines.push(polyline);
          });
        });
      }

      for (const qid in this.items) {
        var item = this.items[qid];
        if (item.osm) continue;
        item.wikidata.markers.forEach((marker_data) => {
          var marker = this.item_has_edit(item) ? greenDarkMarker : redMarker;
          marker_data.marker.setIcon(marker);
        });
      }
    },
    onpopstate(event) {
      var state = event.state;
      if (!state) return;

      this.mode = state.mode;
      this.zoom = state.zoom;
      this.search_text = state.search_text;
      this.center = [state.lat, state.lon];
      this.detail_qid = state.detail_qid;
      this.recent_search = state.recent_search;
      if (!this.detail_qid) this.current_item = undefined;

      this.item_count = state.item_count;
      this.map_area = state.map_area;
      this.hits = state.hits;
      this.current_hit = state.current_hit;

      this.current_osm = state.current_osm;

      this.map.setView(this.center, this.zoom);

      if (this.mode == "search") {
        this.clear_items();
        this.fit_bounds_to_hit(this.current_hit);
      }
    },
  },
  created() {
    var lat = this.startLat ?? 52.19679;
    var lon = this.startLon ?? 0.15224;
    this.center = [lat, lon];
    this.zoom = this.startZoom;
    this.mode = this.startMode;
    this.changeset_comment = this.defaultComment || '+wikidata';
  },
  mounted() {

    this.$nextTick(function () {
      var options = {
        center: this.center,
        zoom: this.zoom || 16,
      };


      var map = L.map("map", options);
      var osm_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
      var tile_url = "https://tile-c.openstreetmap.fr/hot/{z}/{x}/{y}.png";
      var osm = L.tileLayer(osm_url, {
        maxZoom: 19,
      });
      osm.addTo(map);

      var bounds;
      if (this.startRadius) {
        var bounds = L.latLng(this.center).toBounds(this.startRadius * 2000);
        map.fitBounds(bounds);
      } else {
        bounds = map.getBounds();
      }

      map.on("moveend", this.map_moved);
      this.map = map;

      if (this.mode == "search") {
        this.search_text = this.q.trim();
        this.run_search();
      } else {
        this.detail_qid = this.qid_from_url();
        if (this.detail_qid) {
          this.load_wikidata_items(bounds);
        } else {
          this.auto_load(bounds);
        }
        this.update_map_path();
      }

      window.onpopstate = this.onpopstate;
    });

  },
};
</script>

<style>

#select-area-btn {
  position: absolute;
  top: 77px;
  left: 70%;
  transform: translate(-50%, 0);
}


#map {
  position: absolute;
  top: 57px;
  bottom: 0px;
  left: 40%;
  width: 60%;
  z-index: -1;
}

.alert-map {
  position: absolute;
  bottom: 2rem;
  left: 70%;
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
  top: 57px;
  left: 0px;
  bottom: 0px;
  overflow: auto;
  width: 40%;
}

.tag-card-body {
  padding: 0.5rem 0.5rem;
}

</style>
