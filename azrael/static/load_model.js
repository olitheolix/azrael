function endsWith(str, suffix) {
    return str.indexOf(suffix, str.length - suffix.length) !== -1;
}


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
                // Find the first file that ends in JSON. Consider it
                // an error if no such file exists.
                var modelname = null
                for (var idx in obj[frag_name].files) {
                    var fname = obj[frag_name].files[idx]
                    if (!endsWith(fname.toLowerCase(fname), '.json')) continue;
                    modelname = fname;
                    break
                }
                if (modelname == null) {
                    console.log('Worker: did not find RAW json file')
                    model = {'type': null};
                    break
                }

                // All raw fragments are stored in a JSON file on the
                // server called 'model.json'. Download it.
                xmlhttp.open("GET", url + '/' + modelname, false);
                xmlhttp.send();
                try {
                    model = JSON.parse(xmlhttp.responseText);
                    model['type'] = 'RAW';
                } catch (e) {
                    // Usually means the fragments unavailable.
                    // Maybe the object was just deleted.
                    model = {'type': null};
                }
                break;
            case 'DAE':
                model = {'type': 'DAE', 'url': url + '/' + frag_name};
                break;
            case '3JS_V4':
                // Find the first file that ends in JSON. Consider it
                // an error if no such file exists.
                model = null
                for (var idx in obj[frag_name].files) {
                    var fname = obj[frag_name].files[idx]
                    if (!endsWith(fname.toLowerCase(fname), '.json')) continue;

                    model = {'type': '3JS_V4', 'url': url + '/' + fname};
                    break
                }
                if (model == null) {
                    console.log('Worker: did not find 3JS_v4 JSON file')
                    model = {'type': null};
                    break
                }
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
