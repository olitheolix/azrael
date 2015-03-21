onmessage = function (e) {
    // Status message.
    console.log('<load_model.js> Worker received request to download '
                + Object.keys(e.data.objData).length + ' new models');

    // Initialise the output and XMLHttpRequest.
    var out = {};
    var xmlhttp = new XMLHttpRequest();
    
    for (var objID in e.data.objData) {
        var url, tmp;

        // Convenience.
        var obj = e.data.objData[objID];

        // Initialise the fragment hash map for the current object.
        out[objID] = {};

        // Iterate over all fragments, download them, and add them to
        // the just defined `out` object.
        for (var frag_name in obj) {
            // Compile the URL for the fragment. All raw fragments are
            // stored in a JSON file on the server called 'model.json'
            url = e.data.baseURL + obj[frag_name]['url'] + '/model.json';

            // Download the model data for the current fragment.
            xmlhttp.open("GET", url, false);
            xmlhttp.send();
            model = JSON.parse(xmlhttp.responseText);

            // Add the model to the output object.
            out[objID][frag_name] = model;
        }
    }

    // Return all models to the caller.
    postMessage(out);
}
