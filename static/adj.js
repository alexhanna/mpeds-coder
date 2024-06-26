
// Globals
var MAX_CAND_EVENTS = 4;

/**
 * 
 * @param {*} e - Event
 * @param {*} level - Level of the tab (main, sub, etc.)
 * @returns false
 */
var changeTab = function(e, level = "") {
    var label = $(e.target).parent().attr("id").split("_")[0];

    // TODO: Add error checking

    // Get all elements with class="tablinks" and remove the class "active"
    $("." + level + "tablinks").each(function() {
      $(this).removeClass("active");
    });

    // hide all other tab content
    $("." + level + "tab-pane").each(function() {
      $(this).hide();
    });

    // Show the current tab, and add an "active" class to the button that opened the tab
    $('#' + label + "_button").addClass("active");
    $('#' + label + "_block").show();

    // if this has a *, remove
    var button_text = $('#' + label + '_button-link').text();
    if (button_text.indexOf("*") > -1) {
      button_text = button_text.replace("*", "");
      $('#' + label + '_button-link').html(button_text);
    }

    return false;
}

/**
 * Gets the current candidate events in the grid
 * @param {str} to_exclude - candidates to exclude
 * @return {str} - comma-separated string of candidate events
 */
var getCandidates = function(to_exclude = '') {
  // get the current candidate events, minus the one that was clicked
  var candidate_event_ids = []; 
  var cand_events = document.getElementsByClassName('candidate-event');
  for (var i = 0; i < cand_events.length; i++) {
    var id = $(cand_events[i]).attr('id').split('_')[1];
    if (id != to_exclude) {
      candidate_event_ids.push(id);
    }
  }
  return candidate_event_ids.join()
}


/**
 * Loads the grid for adding and removing candidate and canonical events.
 * @param {str} canonical_event_key - Desired canonical event record.
 * @param {str} cand_events_str - Desired candidate events.
 * @returns false on failure, true on success
 */
var loadGrid = function(canonical_event_key = null, cand_events_str = null) {
  var req = $.ajax({
    type: "GET",
    url:  $SCRIPT_ROOT + '/load_adj_grid',
    data: {
      canonical_event_key: canonical_event_key,
      cand_events: cand_events_str
    },
    beforeSend: function () {
      $('.flash').removeClass('alert-danger');
      $('.flash').addClass('alert-info');
      $('.flash').text("Loading...");
      $('.flash').show();
      }
  })
  .done(function() {
    // add HTML to grid
    $('#adj-grid').html(req.responseText);

    // reset URL params
    let search_params = new URLSearchParams(window.location.search);
    search_params.delete('canonical_event_key');
    search_params.append('canonical_event_key', canonical_event_key);
    
    search_params.delete('cand_events');
    search_params.append('cand_events', cand_events_str);
    
    var new_url = 'adj?' + search_params.toString();
    window.history.pushState({path: new_url}, '', new_url);

    // reinitiatize grid listeners
    initializeGridListeners();

    // get rid of loading flash 
    $('.flash').hide();
    $('.flash').removeClass('alert-info');

    return true;
  })
  .fail(function() { return makeError(req.responseText); });

  return true;
}

/**
 * Loads the recent candidate events from the database.
 * @returns true if successful, false otherwise.
 */
var loadRecentCandidateEvents = function() {
  var req = $.ajax({
    url: $SCRIPT_ROOT + '/load_recent_candidate_events',
    type: 'POST'
  })
  .done(function() {
    $('#candidate-recent_block').html(req.responseText);
    return true;
  })
  .fail(function() { return makeError(req.responseText); });
}

/**
 * Loads the recent canonical events from the database.
 * @returns true if successful, false otherwise.
 */
 var loadRecentCanonicalEvents = function() {
  var req = $.ajax({
    url: $SCRIPT_ROOT + '/load_recent_canonical_events',
    type: 'POST'
  })
  .done(function() {
    $('#canonical-recent-search-block').html(req.responseText);
    initializeCanonicalSearchListeners();
    return true;
  })
  .fail(function() { return makeError(req.responseText); });
}

/**
 * Loads the relationship autocomplete listeners and add button.
 * @returns true if successful, false otherwise.
 */
var loadRelationshipListeners = function() {
  // initialize the relationship listeners
  for (var i = 1; i < 4; i++) {
    $("#relationship-key-" + i).autocomplete({
      minlength: 2,
      classes: {
        "ui-autocomplete": "ui-autocomplete-adj"
      },
      source: function(request, response) {
        $.ajax({
          url: $SCRIPT_ROOT + '/search_canonical_autocomplete',
          dataType: "json",
          method: "post",
          data: {
            term: request.term
          },
          success: function(data) {
            if(data.length == 0) {
              data = ["No results round."];
            }
            response(data['result']['data']);
          }
        });
      }
    })
  }

  // initialize the add relationship button
  $('#add-relationship-button').click(function() {
    var req = $.ajax({
      url: $SCRIPT_ROOT + '/add_canonical_relationship',    
      method: "POST",
      data: {
        key1: $('#relationship-key-1').val(),
        key2: $('#relationship-key-2').val(),
        type: $('#relationship-type').val()
      }
    })
    .done(function() {
      return makeSuccess("Relationship added.");
    })
    .fail(function() { return makeError(req.responseText); });
  });

  // view hierarchy button
  $('#view-hierarchy-button').click(function() {
    var req = $.ajax({
      url: $SCRIPT_ROOT + '/load_canonical_hierarchy',
      method: "POST",
      data: {
        key: $('#relationship-key-3').val()
      }
    })
    .done(function() {
      $('#view-hierarchy').html(req.responseText);

      // add the grid listeners to the hierarchy view
      $('.hierarchy-wrapper .glyphicon-export').click(function() {
        var canonical_event_key = $(this).parent().attr('data-key');
        loadGrid(canonical_event_key, getCandidates());
      });

      // add delete listeners to the hierarchy view
      $('.hierarchy-parent .glyphicon-trash').click(function(e) {
        r = confirm("Are you sure you want to delete this relationship?");
        if (r == true) {
          var parent_div = $(this).closest('.hierarchy-parent');
          var req = $.ajax({
            url: $SCRIPT_ROOT + '/delete_canonical_relationship',
            method: "POST",
            data: {
              id1: $(this).closest('.hierarchy-wrapper').attr('data-id'),
              id2: parent_div.attr('data-id'),
              type: parent_div.attr('data-type')
            }
          })
          .done(function() {
            parent_div.remove();
            return makeSuccess("Relationship deleted.");
          })
          .fail(function() { return makeError(req.responseText); });
        }
      });

      $('.hierarchy-child .glyphicon-trash').click(function(e) {
        r = confirm("Are you sure you want to delete this relationship?");
        if (r == true) {
          var child_div = $(this).closest('.hierarchy-child');
          var req = $.ajax({
            url: $SCRIPT_ROOT + '/delete_canonical_relationship',
            method: "POST",
            data: {
              id1: child_div.attr('data-id'),
              id2: $(this).closest('.hierarchy-wrapper').attr('data-id'),
              type: child_div.attr('data-type')
            }
          })
          .done(function() {
            child_div.remove();
            return makeSuccess("Relationship deleted.");
          })
          .fail(function() { return makeError(req.responseText); });
        }
      });
    })
  .fail(function() { return makeError(req.responseText); });
  });
}

/**
 * Loads the search results for the given query from the existing forms.
 * @returns true if successful, false otherwise.
 */
 var loadSearch = function(search_mode) {
  var req = $.ajax({
    url: $SCRIPT_ROOT + '/do_search/' + search_mode,
    type: "POST",
    data: 
      $('#' + search_mode + '_search_form, ' + 
        '#' + search_mode + '_filter_form, ' + 
        '#' + search_mode + '_sort_form').serialize(),
    beforeSend: function () {
      $('.flash').removeClass('alert-danger');
      $('.flash').addClass('alert-info');
      $('.flash').text("Loading...");
      $('.flash').show();
    }
  })
  .done(function() {
    // Update content block.
    $('#' + search_mode + '-search_block').html(req.responseText); 

    // Update the search button text.
    n_results = req.getResponseHeader('Search-Results');
    $('#' + search_mode + '-search-text').text("Search (" + n_results + " results)");

    // Update the button text.
    var button_text = $('#' + search_mode + '_button-link').text();
    if($('#' + search_mode + '_button-link').text().indexOf('*') < 0) {
      $('#' + search_mode + '_button-link').text(button_text + '*');
    }

    // Update the URL search params.
    let curr_search_params = new URLSearchParams(window.location.search);
    var search_params = jQuery.parseJSON(req.getResponseHeader('Query'));
    for (var key in search_params) {
      curr_search_params.set(key, search_params[key]);
    }

    var new_url = 'adj?' + curr_search_params.toString();
    window.history.pushState({path: new_url}, '', new_url);

    markGridEvents();
    initializeSearchListeners();

    // get rid of loading flash 
    $('.flash').hide();
    $('.flash').removeClass('alert-info');
    return true;
  })
  .fail(function() { return makeError(req.responseText); });
}

/**
 * Prevents the user from submitting the form by pressing enter.
 * @param event The keypress event.
 * @returns true if the keypress was handled, false otherwise.
 */
var preventEnter = function(e) {
  var keyCode = e.keyCode || e.which;
  if (keyCode == 13) {
    e.preventDefault();
    return false;
  }
}

/**
 * Removes the block from the canonical record.
 * @returns true if successful, false otherwise.
 */
 var removeCanonical = function () {
  var target = $(this).closest('.expanded-event-variable');
  var cel_id = target.attr('data-key');
  var variable = target.attr('data-var');
  var block_id = '#canonical-' + variable + '_' + cel_id;

  var req = $.ajax({
    type: 'POST',
    url: $SCRIPT_ROOT + '/del_canonical_record',
    data: {
      cel_id: cel_id
    }
  })
  .done(function() {
    // remove block
    $(block_id).remove();
    return true;
  })
  .fail(function() { return makeError(req.responseText); });
}


/**
 * Toggles flags for candidate events.
 * @param {Event} e - click event
 * @param {str} operation - add or deletion operation. takes values 'add' or 'del'
 * @param {str} flag - the flag to add to this event
 * @returns true if successful, false otherwise.
 */
var toggleFlag = function(e, operation, flag) {
  if (operation != 'add' & operation != 'del') {
    return false;
  }

  var column = $(e.target).closest('.candidate-event');
  var req = $.ajax({
    type: 'POST',
    url: $SCRIPT_ROOT + '/' + operation + '_event_flag',
    data: {
      event_id: column.attr('data-event'), 
      flag: flag
    }
  })
  .done(function() { 
    // remove this event if we're adding a completed flag
    to_exclude = '';
    if (operation == 'add' & flag == 'completed') {
      to_exclude = column.attr('data-event');
    }

    loadGrid(
      canonical_event_key = $('div.canonical-event-metadata').attr('data-key'),
      cand_event_str = getCandidates(to_exclude)
    );
    loadSearch('candidate');
  })
  .fail(function() { return makeError(req.responseText); });
}


/**
 * 
 * @param {str} mode - add or edit 
 */
var updateModal = function (variable, mode) {
  var req = $.ajax({
    type: "POST",
    url: $SCRIPT_ROOT + '/modal_edit/' + variable + '/' + mode,
    data: $('#modal-form').serialize()
  })
  .done(function() {
    $("#modal-flash").text("Added successfully.");
    $("#modal-flash").removeClass("alert-danger");
    $("#modal-flash").addClass("alert-success");
    $("#modal-flash").show();
    $('#modal-container').modal('hide');

    // update the grid with new canonical event if it exists
    var reload_key = null;
    if($("#canonical-event-key").val() !== undefined) {
      reload_key = $("#canonical-event-key").val();
    } else {
      // otherwise, reload the current grid
      reload_key = $('.canonical-event-metadata').attr('data-key');
    }

    loadGrid(
      canonical_event_key = reload_key,
      cand_events_str = getCandidates()
    );
    loadRecentCanonicalEvents();
  })
  .fail(function() {
    $("#modal-flash").text(req.responseText);
    $("#modal-flash").addClass("alert-danger");
    $("#modal-flash").show();
  });
}

/**
 * Makes an success flash message.
 * @param {str} msg - Message to show. 
 */
 var makeSuccess = function(msg) {
  $('.flash').removeClass('alert-danger');
  $('.flash').addClass('alert-success');
  $('.flash').text(msg);
  $('.flash').show();
  $('.flash').fadeOut(5000);
  return true;
}

/**
 * Makes an error flash message.
 * @param {str} msg - Message to show. 
 */
var makeError = function(msg) {
  $('.flash').removeClass('alert-success');
  $('.flash').addClass('alert-danger');
  $('.flash').text(msg);
  $('.flash').show();
  $('.flash').fadeOut(5000);
  return false;
}

/**
 * Marks the given candidate events as in the grid.
 * @param {str} cand_events - optional array of candidate event ids.
 *  */
var markGridEvents = function(cand_events = null) {
  // If we don't get cand_events, get them from the URL.
  if(cand_events == null) {
    var search_params = new URLSearchParams(window.location.search);
    cand_events = search_params.get('cand_events').split(',');
  }

  // Mark all events as not in the grid.
  $('.event-desc.candidate-search').each(function() {
    $(this).find('.cand-isactive').hide();
    $(this).find('.cand-makeactive').show();
  });

  // Mark events which are in the grid as active.
  for (var i = 0; i < cand_events.length; i++) {
    let event_desc = $('.event-desc[data-event="' + cand_events[i] + '"]');
    event_desc.find('.cand-isactive').show();
    event_desc.find('.cand-makeactive').hide();
  }
}

/**
 * Marks the given canonical event as in the grid.
 * @param {str} event_desc - optional element to mark as active.
 */
var markCanonicalGridEvent = function(event_desc = null) {
  // Mark all canonical event search results as not in the grid.
  $('.event-desc.canonical-search').each(function() {
    $(this).find('.canonical-isactive').hide();
    $(this).find('.canonical-makeactive').show();
  });

  // Mark the current canonical event as active.
  if (event_desc != null) {
    event_desc.find('.canonical-isactive').show();
    event_desc.find('.canonical-makeactive').hide();
  }
};

/**
 * 
 * @param {*} e - event
 * @param {*} variable - variable to be expanded
 */
var expandDesc = function(e, variable) {
  $('.expanded-event-variable[data-var=' + variable + ']').each(function() {
    $(this).addClass('maximize');
  });

  $('#expand-' + variable).hide();
  $('#collapse-' + variable).show();
}

/**
 * 
 * @param {*} e - event 
 * @param {*} variable - variable to be collapse
 */
var collapseDesc = function(e, variable) {
  $('.expanded-event-variable[data-var=' + variable + ']').each(function() {
    $(this).removeClass('maximize');
  });

  $('#expand-' + variable).show();
  $('#collapse-' + variable).hide();
}

/**
 * Update the grid with a candidate event.
 * Gets the current params from URL and replaces the last event.
 * @param {str} event_id - event id to add to the grid.
 * 
 * @returns {bool} - true if successful, false otherwise.
 */
var updateGridWithCandidateEvent = function(event_id) {
  var search_params = new URLSearchParams(window.location.search);
  var cand_events = search_params.get('cand_events').split(',');  

  // remove last event from the list if full
  if (cand_events.includes(event_id)) {
    return makeError("Event already in grid.");
  } else if (cand_events.length == MAX_CAND_EVENTS) {
    cand_events.pop();
  } else if (cand_events.length == 1 & (cand_events[0] == 'null' | cand_events[0] == '')) {
    // remove the null keyword
    cand_events = [];
  } 

  // add this event to the list
  cand_events.push(event_id);

  return loadGrid(
    canonical_event_key = search_params.get('canonical_event_key'),
    cand_events_str = cand_events.join(',')
  );
}

/**
 * Initialize listeners for search pane.
 * Will need to perform this on every reload of the search pane.
 * 
 */
var initializeSearchListeners = function() {
  // listeners for current search results
  $('.cand-makeactive').click(function(e) {
    e.preventDefault();
    var event_desc = $(e.target).closest('.event-desc');
    var event_id = event_desc.attr('data-event');

    let success = updateGridWithCandidateEvent(event_id);

    if (success) {
      markGridEvents(cand_events);
      loadRecentCandidateEvents();
    }

    return true;
  });
}

/**
 * Initialize canonical search listeners.
 */
var initializeCanonicalSearchListeners = function() {
  // Listener for canonical event search.
  $('.canonical-makeactive').click(function (e) {
    e.preventDefault();

    // get event desc
    var event_desc = $(e.target).closest('.event-desc');

    // get key and id from event-desc
    var canonical_event_key = event_desc.attr('data-key');
    
    var success = loadGrid(
      canonical_event_key = canonical_event_key, 
      cand_events_str = getCandidates()
    );

    if (success) {
      markCanonicalGridEvent(event_desc);
      loadRecentCanonicalEvents();
    }
  });

  $('.canonical-cand-makeactive').click(function (e) {
    e.preventDefault()

    var event_id = $(e.target).attr('data-event');
    let success = updateGridWithCandidateEvent(event_id);

    if (success) {
      loadRecentCandidateEvents();
    }
  });
}

/**
 * Initialize listeners for grid buttons.
 * Need to perform this on load and on reload of grid.
 */
var initializeGridListeners = function() {
  /**
   * Additions
   */

  // Add a value to current canonical event
  $('.add-val').click(function(e) {
    var canonical_event_id = $('div.canonical-event-metadata').attr('id').split('_')[1];
    var variable = $(e.target).closest('.expanded-event-variable').attr('data-var').split('_')[0];

    // No canonical event, so error
    if (canonical_event_id == '') {
      makeError("Please select a canonical event first.");
      return false;
    }

    var req = $.ajax({
      type: 'POST',
      url: $SCRIPT_ROOT + '/add_canonical_record',
      data: {
        canonical_event_id: canonical_event_id,
        cec_id: $(e.target).attr('data-key')
      }
    })
    .done(function() {
      // remove the none block if it exists
      $('#canonical-event_' + variable + ' .none').remove();

      // make a block variable for the text and get ID
      var block = req.responseText;

      // add block to the canonical event variable
      $('#canonical-event_' + variable).append(block);

      // add remove listener by finding the last element 
      // added to this group of canonical cells
      var cells = $('#canonical-event_' + variable).children();
      $(cells[cells.length - 1]).find('a.remove-canonical').click(removeCanonical);
      return true;
    })
    .fail(function() { return makeError(req.responseText); });
  });

  // Link this event candidate event to the current canonical event
  $('.add-link').click(function(e) {
    var canonical_event_id = $('div.canonical-event-metadata').attr('id').split('_')[1];
    if (canonical_event_id == '') {
      makeError("Please select a canonical event first.");
      return false;
    }

    var column = $(e.target).closest('.candidate-event');
    var req = $.ajax({
      type: 'POST',
      url: $SCRIPT_ROOT + '/add_canonical_link',
      data: {
        canonical_event_id: canonical_event_id,
        article_id: column.attr('data-article')
      }
    })
    .done(function() { 
      loadGrid(
        canonical_event_key = $('div.canonical-event-metadata').attr('data-key'),
        cand_event_str = getCandidates()
      );
    })
    .fail(function() { return makeError(req.responseText); });
  });

  // add completed flag to candidate event
  $('.add-completed').click(function(e) { 
    toggleFlag(e, 'add', 'completed');
  });

  // add further review flag to candidate event
  $('.add-flag').click(function(e) { 
    toggleFlag(e, 'add', 'for-review');
  });

  // add value to a new dummy event
  $('.add-dummy').click(function(e) {
    var variable = $(e.target).closest('.expanded-event-variable-name').attr('data-var');
    var canonical_event_key = $('.canonical-event-metadata').attr('data-key');

    if(canonical_event_key == '') {
      makeError("Please select a canonical event first.");
      return false;
    }

    var req = $.ajax({
      type: 'POST',
      url: $SCRIPT_ROOT + '/modal_view',
      data: {
        candidate_event_ids: getCandidates(),
        variable: variable,
        key: canonical_event_key
      }
    })
    .done(function() {
      $('#modal-container .modal-content').html(req.responseText);
      $('#modal-container').modal('show');

      // add date pickers
      $('#modal-container .date').datetimepicker({ format: 'YYYY-MM-DD' });        

      $('#modal-submit').click(function(e) {
        e.preventDefault(); 
        updateModal(variable, 'add');
      });
    })
    .fail(function() { return makeError("Could not load modal."); })
  });

  // Select all text in the current candidate event box.
  $('.select-text').click(function(e) {
    e.preventDefault();

    var text = $(e.target).closest('.expanded-event-variable');
    let range = document.createRange();
    range.selectNodeContents(text[0]);
    window.getSelection().addRange(range);
  });

  // edit a canonical event metadata
  $('.edit-canonical').click(function(e) {
    var canonical_event_key = $(e.target).closest('.canonical-event-metadata').attr('data-key');
    var req = $.ajax({
      type: 'POST',
      url: $SCRIPT_ROOT + '/modal_view',
      data: {
        variable: 'canonical',
        key: canonical_event_key,
        edit: true
      }
    })
    .done(function() {
      $('#modal-container .modal-content').html(req.responseText);
      $('#modal-container').modal('show');

      // prevent pressing enter on the key from submitting the form
      $('#canonical-event-key').on('keyup keypress', function(e) {
        preventEnter(e)
      });

      $('#modal-submit').click(function(e) { 
        e.preventDefault(); 
        updateModal('canonical', 'edit'); 
      });

      // Delete canonical event 
      $('#modal-delete').click(function () {
        var r = confirm("Are you sure you want to delete the current canonical event?")
        if (r == false) {
          return;
        }

        // remove from the database via Ajax call
        var req = $.ajax({
          url: $SCRIPT_ROOT + '/delete_canonical',
          type: "POST",
          data: {
            key: canonical_event_key
          }
        })
        .done(function() {
          $('#modal-container').modal('hide');

          loadGrid('', getCandidates());
          loadRecentCanonicalEvents(); 
          return makeSuccess(req.responseText);
        })
        .fail(function() { return makeError(req.responseText); });
      });
    })
    .fail(function() { return makeError("Could not load modal."); })
  });

  // Toggle metadata visibility.
  $('#hide-metadata').click(function(e) {
    $('.expanded-event-variable-metadata').hide();
    $('.canonical-event-metadata .expanded-event-variable').hide();
    $('#show-metadata').show();
    $('#hide-metadata').hide();
  });

  $('#show-metadata').click(function(e) {
    $('.expanded-event-variable-metadata').show();
    $('.canonical-event-metadata .expanded-event-variable').show();
    $('#show-metadata').hide();
    $('#hide-metadata').show();
  });

  // Toggle the expansion of the article-desc and the desc.
  $('#expand-article-desc').click(function(e) { expandDesc(e, 'article-desc') }); 
  $('#expand-desc').click(function(e) { expandDesc(e, 'desc') }); 
  $('#collapse-article-desc').click(function(e) { collapseDesc(e, 'article-desc') });
  $('#collapse-desc').click(function(e) { collapseDesc(e, 'desc') });

  /**
   * Deletions and removals
   */

  // remove value from current canonical event
  $('.remove-canonical').click(removeCanonical);

  // Remove candidate event from grid
  $('.remove-candidate').click(function() {
      // get current canonical key, if it exists
      var canonical_event_key = $('div.canonical-event-metadata');
      if (canonical_event_key) {
        canonical_event_key = canonical_event_key.attr('data-key');
      }

      // the current event to exclude
      var cand_metadata = $(this).closest('.candidate-event');
      var to_exclude = cand_metadata.attr('id').split('_')[1];
      
      loadGrid(
          canonical_event_key = canonical_event_key, 
          cand_event_str = getCandidates(to_exclude)
      );

      markGridEvents();
  });

  // Remove the link to this canonical event
  $('.remove-link').click(function (e) {
    var req = $.ajax({
      type: 'POST',
      url: $SCRIPT_ROOT + '/del_canonical_link',
      data: {
        article_id: $(e.target).attr('data-article')
      }
    })
    .done(function() {
      loadGrid(
        canonical_event_key = $('div.canonical-event-metadata').attr('data-key'),
        cand_event_str = getCandidates()
      );
    })
    .fail(function() { return makeError(req.responseText); });    
  });

  // Remove completed
  $('.remove-completed').click(function(e) { 
    toggleFlag(e, 'del', 'completed');
  });

  // Remove flag
  $('.remove-flag').click(function(e) { 
    toggleFlag(e, 'del', 'for-review');
  });

  // Remove canonical event from grid
  $('div.canonical-event-metadata a.glyphicon-remove-sign').click(function () {
    var success = loadGrid('', getCandidates());

    // Change the buttons in the search section
    if (success) {
      markCanonicalGridEvent();
    }
  });
}

// MAIN -- document ready 
$(function () { 
    // Show search block first
    $("#search_block").show();

    // Add listener to tab links 
    $(".tablinks").each(function(){
        $(this).click(changeTab);
    });

    // Add listener to subtab links 
    var subtabs = ['search', 'cand', 'canonical'];
    subtabs.forEach(function(curr){
      $('.' + curr + '-subtablinks').each(function(){
        $(this).click(function(e) { changeTab(e, curr + '-sub'); });
      });
    });

    // hide search panel
    $("#cand-events-hide").click(function() {
      $("#adj-pane-cand-events").hide();
      $("#cand-events-hide").hide();
      $("#cand-events-show").show();

      $("#adj-pane-expanded-view").removeClass("col-md-7");
      $("#adj-pane-expanded-view").addClass("col-md-12");
    });

    // show search pane
    $("#cand-events-show").click(function() {
      $("#cand-events-show").hide();
      $("#cand-events-hide").show();
      $("#adj-pane-cand-events").show();

      $("#adj-pane-expanded-view").removeClass("col-md-12");
      $("#adj-pane-expanded-view").addClass("col-md-7");
    });

    // Listener to create a new canonical event
    $('#new-canonical').click(function () {;
      var req = $.ajax({
        url: $SCRIPT_ROOT + '/modal_view', 
        type: "POST",
        data: {
          variable: 'canonical'
        }
      })
      .done(function() {
        $('#modal-container .modal-content').html(req.responseText);
        $('#modal-container').modal('show');

        // prevent pressing enter on the key from submitting the form
        $('#canonical-event-key').on('keyup keypress', function(e) {
          preventEnter(e)
        });

        $('#modal-submit').click(function(e) {
          e.preventDefault(); 
          updateModal('canonical', 'add');
        });
      })
    });

    // Listener for search button.
    $('#candidate_search_button').click(function(e) { 
      e.preventDefault();
      loadSearch('candidate'); 
    });

    // Listener for clear button.
    $('.clear-values').each(function() {
      $(this).click(function() {
        // Clear the search form and clear URL parameters
        let search_params = new URLSearchParams(window.location.search);

        $(this).closest('.form-row').find('input').each(function() {
          $(this).val('');
          search_params.set($(this).attr('name'), '');
        });
        $(this).closest('.form-row').find('select').each(function() {
          $(this).val('');
          search_params.set($(this).attr('name'), '');
        });

        // Update the URL with cleared values
        var new_url = 'adj?' + search_params.toString();
        window.history.pushState({path: new_url}, '', new_url);    
      });
    });

    // Listener for canonical event search
    $('#canonical_search_button').click(function(e) {
      e.preventDefault();
      // Get the candidates from the database
      var req = $.ajax({
        url: $SCRIPT_ROOT + '/do_search/canonical',
        type: "POST",
        data: $('#canonical_search_form, ' + 
          '#canonical_filter_form, ' + 
          '#canonical_sort_form').serialize(),
        beforeSend: function () {
          $('.flash').removeClass('alert-danger');
          $('.flash').addClass('alert-info');
          $('.flash').text("Loading...");
          $('.flash').show();
          }
      })
      .done(function() {
        // Update the canonical events in the search list
        $('#canonical-search_block').html(req.responseText);

        // Update the search button text.
        n_results = req.getResponseHeader('Search-Results');
        $('#canonical-search-text').text("Search (" + n_results + " results)");

        // Update the canonical button text.
        var button_text = $('#canonical_button-link').text();
        if($('#canonical_button-link').text().indexOf('*') < 0) {
          $('#canonical_button-link').text(button_text + '*');
        }

        // Initialize the listeners for the new canonical search results
        initializeCanonicalSearchListeners();

        // Listener for canonical select all button
        $('#canonical-selectall-button').click(function(e) {
          e.preventDefault();
          $('.export-checkbox').each(function () { 
            $(this).prop('checked', true); 
          });
        });

        // Listener for canonical select none button
        $('#canonical-selectnone-button').click(function(e) {
          e.preventDefault();
          $('.export-checkbox').each(function () { 
            $(this).prop('checked', false); 
          });
        });

        // Listener for canonical export button
        $('#canonical-export-button').click(function(e) {
          e.preventDefault();
          
          var events = $('.export-checkbox:checked');

          // make sure something is checked
          if (typeof events !== 'undefined' && events.length > 0) {
            var event_ids = [];
            events.each(function() {
              event_ids.push($(this).val());
            });

            var req = $.ajax({
              url: $SCRIPT_ROOT + '/download_canonical/' + event_ids.join(','), 
              type: "GET"
            })
            .done(function() {
              window.location.href = $SCRIPT_ROOT + '/download_canonical/' + event_ids.join(',');
            });
          } else {
            return makeError('Please select at least one event to export.');
          }
        });

        // get rid of loading flash 
        $('.flash').hide();
        $('.flash').removeClass('alert-info');
        return true;
      })
      .fail(function() { return makeError(req.responseText); });      
    });

    // Hide canonical search to begin
    $('#search-canonical_block').hide();

    // initialize the grid and search 
    let search_params = new URLSearchParams(window.location.search);
    var repeated_fields = [
      'filter_compare',
      'filter_value',
      'filter_field',
      'sort_field',
      'sort_order'
    ];
    var search_ids = ['candidate_search_input'];

    // create indexed array of search parameters
    for(var i = 0; i < 3; i++) {
      for (var j = 0; j < repeated_fields.length; j++) {
        var field = 'candidate_' + repeated_fields[j] + '_' + i;
        search_ids.push(field);
      }
    }

    // initialize the search parameters in the URLs
    for(var i = 0; i < search_ids.length; i++) {
      $('#' + search_ids[i]).val(search_params.get(search_ids[i]));
    }

    loadSearch('candidate');
    loadGrid(
      search_params.get('canonical_event_key'),      
      search_params.get('cand_events')
    );
    loadRecentCandidateEvents();
    loadRecentCanonicalEvents();
    loadRelationshipListeners();
});