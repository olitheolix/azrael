onmessage = function (e) {
    // Status message.
    console.log('<load_model.js> Worker received request to download '
                + Object.keys(e.data.objData).length + ' new models');

    // Initialise the output and XMLHttpRequest.
    var out = {};
    var xmlhttp = new XMLHttpRequest();
    
    for (var objID in e.data.objData) {
        var url, tmp, model;

        // Convenience.
        var obj = e.data.objData[objID];

        // Initialise the fragment hash map for the current object.
        out[objID] = {};

        // Iterate over all fragments, download them, and add them to
        // the just defined `out` object.
        for (var frag_name in obj) {
            url = e.data.baseURL + obj[frag_name]['url_frag']
            switch (obj[frag_name].fragtype) {
            case 'RAW':
                // All raw fragments are stored in a JSON file on the
                // server called 'model.json'. Download it.
                xmlhttp.open("GET", url + '/model.json', false);
                xmlhttp.send();
                try {
                    model = JSON.parse(xmlhttp.responseText);
                    model['type'] = 'RAW';
                } catch (e) {
                    // Usually means the fragmetns were not available
                    // anymore, most likely because the object has
                    // been deleted in the meantime.
                    model = {'type': null};
                }
                break;
            case 'DAE':
                model = {'type': 'DAE', 'url': url + '/' + frag_name};
                break;
            default:
                model = {'type': null};
            }

            // Add the model to the output object.
            out[objID][frag_name] = model;
        }
    }

    // Return all models to the caller.
    postMessage(out);
}
