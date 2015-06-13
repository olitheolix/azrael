var StateVariable = function(pos, vel, orientation, scale, imass) {
    var d = {'radius': scale,
         'scale': scale,
         'imass': imass,
         'restitution': 0.9,
         'orientation': orientation,
         'position': pos,
         'velocityLin': vel,
         'velocityRot': [0, 0, 0],
         'cshapes': [0, 1, 1, 1]};
    return d
}

/*
  Create a ThreeJS geometry object.
*/
function compileMesh (objID, vert, uv, rgb, scale) {
    var geo = new THREE.Geometry()

    console.log('Compiling mesh with ' + vert.length + ' vertices');

    // Apply the scaling.
    for (ii=0; ii < vert.length; ii ++) vert[ii] *= scale;

    // Determine if there are any UV coordinates available.
    var hasUV = (uv.length > 0)
    var hasRGB = (rgb.length > 0)

    // Compile the geometry.
    geo.faceVertexUvs[0] = []
    var uvIdx = 0
    for (ii=0; ii < vert.length; ii += 9) {
        // Add the three vertices that define a triangle.
        var v1 = new THREE.Vector3(vert[ii+0], vert[ii+1], vert[ii+2])
        var v2 = new THREE.Vector3(vert[ii+3], vert[ii+4], vert[ii+5])
        var v3 = new THREE.Vector3(vert[ii+6], vert[ii+7], vert[ii+8])
        geo.vertices.push(v1, v2, v3);

        // Add UV coordinates if they are available.
        if (hasUV) {
            geo.faceVertexUvs[0].push([
                new THREE.Vector2(uv[uvIdx+0], uv[uvIdx+1]),
                new THREE.Vector2(uv[uvIdx+2], uv[uvIdx+3]),
                new THREE.Vector2(uv[uvIdx+4], uv[uvIdx+5])])
            uvIdx += 6
        }

        // Define the current face in terms of the three just added vertices.
        var facecnt = Math.floor(ii / 3)
        geo.faces.push( new THREE.Face3(facecnt, facecnt+1, facecnt+2))
    }

    // Assign the face colors, either via directly specified colors or a texture map.
    if (!hasUV) {
        for (var i = 0; i < geo.faces.length; i++) {
            var face = geo.faces[i];
            if (hasRGB) {
                // No UV map, but RGB values are available: use them
                // for the face colours. The multiplier of 9 is necessary
                // because the RGB array from Azrael specifes the
                // color of each vertex, whereas here we only specify
                // the color of the entire triangle.
                face.color.setRGB(rgb[9 * i] / 255, rgb[9 * i + 1] / 255, rgb[9 * i + 2] / 255);
            } else {
                // No UV map, no RGB values: assign random face colours.
                face.color.setHex(Math.random() * 0xffffff);
            }
        }

        // Build a new object in ThreeJS.
        var mat = new THREE.MeshBasicMaterial(
            {'vertexColors': THREE.FaceColors,
             'wireframe': false,
             'wireframeLinewidth': 3})
    } else {
        // Create a textured material.
        var fname = 'img/texture_' + objID + '.jpg'
        var texture = THREE.ImageUtils.loadTexture(fname);
        var mat = new THREE.MeshBasicMaterial({
            'map': texture,
            'wireframe': false,
            'overdraw': true
        })
    }

    return new THREE.Mesh(geo, mat)
}

/*
Proof-of-concept function only to test downloading the geometry
directly via an URL instead of via Clacks.

The returned value is the same structure than that of "getGeometry".
Example: download geometry and build the ThreeJS mesh.

  >> msg = getGeometryFromURL("http://localhost:8080/templates/ground_geo");
  >> ...
  >> var new_geo = compileMesh(objID, msg.vert, msg.UV, scale);

*/
var getGeometryFromURL = function (url) {
    xmlhttp = new XMLHttpRequest();
    xmlhttp.open("GET", url, false);
    xmlhttp.send();
    var tmp = JSON.parse(xmlhttp.responseText);
    return {'ok': true, 'data': tmp}
}


var getGeometryCube = function () {
    buf_vert = [
        -1.0, -1.0, -1.0,   -1.0, -1.0, +1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, -1.0,   -1.0, -1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,   +1.0, -1.0, -1.0,
        +1.0, +1.0, -1.0,   +1.0, -1.0, -1.0,   -1.0, -1.0, -1.0,
        -1.0, -1.0, -1.0,   -1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,
        -1.0, +1.0, +1.0,   -1.0, -1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   +1.0, -1.0, -1.0,   +1.0, +1.0, -1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   +1.0, +1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, +1.0,   +1.0, -1.0, +1.0];

    for (ii=0; ii < buf_vert.length; ii++) {
        buf_vert[ii] *= 0.5;
    }
    return buf_vert;
}

/* ------------------------------------------------------------
   Commands to Clacks/Clerk
 ------------------------------------------------------------ */

function ping() {
    var cmd = JSON.stringify({'cmd': 'ping_clacks', 'payload': {}})
    var dec = function (msg) {
        return JSON.parse(msg.data)
    };
    return [cmd, dec]
}


function suggestPosition(objID, pos) {
    var cmd = JSON.stringify({'cmd': 'suggest_pos',
                              'payload': {'objID': objID, 'pos': pos}})
    var dec = function (msg) {
        return JSON.parse(msg.data)
    };
    return [cmd, dec]
}


function getTemplate(templateID) {
    var cmd = {'cmd': 'get_template', 'payload': {'templateID': templateID}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok,
                'vert': parsed.payload.vert,
                'UV': parsed.payload.UV,
                'RGB': parsed.payload.RGB,
                'cs': parsed.payload.cs}
    };

    return [cmd, dec]
}

function getGeometry(objIDs) {
    var cmd = {'cmd': 'get_fragment_geometries', 'payload': {'objIDs': objIDs}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok, 'data': parsed.payload}
    };

    return [cmd, dec]
}

function addTemplate(templateID, cs, vertices) {
    var cmd = {'cmd': 'add_template', 'data':
               {'id': templateID, 'cs': cs, 'vert': vertices,
                'UV': [], 'RGB': [], 'boosters': [], 'factories': []}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok}
    };
    return [cmd, dec]
}

function spawn(templateID, pos, vel, orient, scale, imass) {
    var sv = StateVariable(pos, vel, orient, scale, imass)
    sv.cshapes = [4, 1, 1, 1]

    var payload = {'id': null, 'templateID': templateID, 'sv': sv}
    var cmd = {'cmd': 'spawn', 'payload': payload}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok, 'objID': parsed.payload.objID}
    };
    return [cmd, dec]
}

function getAllObjectIDs() {
    var cmd = {'cmd': 'get_all_objids', 'payload': {}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok, 'objIDs': parsed.payload.objIDs}
    };
    return [cmd, dec]
}

function getTemplateID(objID) {
    var cmd = {'cmd': 'get_template_id', 'payload': {'objID': objID}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok, 'templateID': parsed.payload.templateID}
    };
    return [cmd, dec]
}

function getStateVariable(objID) {
    var cmd = {'cmd': 'get_body_states', 'payload': {'objIDs': objID}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok, 'sv': parsed.payload.data}
    };
    return [cmd, dec]
}


function getAllStateVariables() {
    var cmd = {'cmd': 'get_all_body_states', 'payload': {}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok, 'data': parsed.payload.data}
    };
    return [cmd, dec]
}


function arrayEqual(arr1, arr2) {
    if ((arr1 == undefined) || (arr2 == undefined)) return false;
    if (arr1.length != arr2.length) return false;
    var isequal = true
    for (var jj in arr1) {
        if (arr1[jj] != arr2[jj]) {
            isequal = false;
            break;
        }
    }
    return isequal;
}

// Update the position and orientation of each fragment. Both are a
// function of the object's position and orientation in world
// coordinates as well as the position and orientation of the fragment
// in object coordinates.  The exact formula for the position is:
// 
//   P = objPos + objScl * objRot * fragPos;
//   R = objRot * fragRot;
//   S = objScl * fragScl;
// 
// You can easily derive them by chaining the transformations for a
// position vector V:
// 
//   fragV = fragPos + fragRot * fragScl * V       (1)
//   finV = objPos + objRot * objScal * fragV      (2)
// 
// Plug (1) into (2) and multiply the terms to obtain:
// 
//   finV = objPos * objScal * objRot * fragPos + ...
//          ... + objRot * fragRot * objScl * fragScl * V
// 
// or in terms of the previously defined P, R, and S:
//   finV = P + R * S * V
function updateObjectGeometries(objID, allSVs, obj_cache) {
    // Convenience.
    var sv = allSVs[objID]['sv']

    // Compile a hash map for all fragments with the
    // fragment-name as the key. We will need this below to
    // look up Fragments directly instead of searching through
    // the array every time.
    var fragData = {};
    for (var ii in allSVs[objID]['frag']) {
        var fragname = allSVs[objID]['frag'][ii]['id'];
        fragData[fragname] = allSVs[objID]['frag'][ii];
    }

    // Pre-allocate the necessary ThreeJS Vector/Quaternion objects.
    var objPos = new THREE.Vector3(),
        objRot = new THREE.Quaternion(),
        fragPos = new THREE.Vector3(),
        fragRot = new THREE.Quaternion(),
        objScl = new THREE.Vector3(sv.scale, sv.scale, sv.scale),
        fragScl = new THREE.Vector3(1, 1, 1),
        P = 0,
        R = 0,
        S = 0;

    // Assign the object- position and quaternion to JS variables.
    for (var fragname in obj_cache[objID]) {
        // Convert the Azrael data to ThreeJS types.
        fragPos = fragPos.fromArray(fragData[fragname]['position']);
        fragRot = fragRot.fromArray(fragData[fragname]['orientation']);
        fragScl.x = fragData[fragname]['scale'];
        fragScl.y = fragData[fragname]['scale'];
        fragScl.z = fragData[fragname]['scale'];
        objPos = objPos.fromArray(sv.position);
        objRot = objRot.fromArray(sv.orientation);
        objScl = objScl.set(sv.scale, sv.scale, sv.scale);

        // Position: objPos + objScl * objRot * fragPos
        P = fragPos.applyQuaternion(objRot);
        P = P.multiply(objScl);
        P = P.add(objPos);

        // Quaternion: objRot * fragRot
        R = fragRot.multiplyQuaternions(objRot, fragRot);

        // Scale: objScl * fragScl
        S = objScl.multiply(fragScl);

        // Update position, orientation, and scale of the object.
        obj_cache[objID][fragname].position.copy(P);
        obj_cache[objID][fragname].quaternion.copy(R);
        obj_cache[objID][fragname].scale.copy(S);

        // Hide the object altogether if its overall scale is
        // too small. This is merely a hack to avoid problems
        // with a ThreeJS internal matrix inversions somewhere.
        if (S.lengthSq() < Math.pow(0.01, 2)) {
            obj_cache[objID][fragname].visible = false;
        } else {
            obj_cache[objID][fragname].visible = true;
        }
        obj_cache[objID][fragname].verticesNeedUpdate = true;
    }
}

/* ------------------------------------------------------------
   Command flow for one frame.
 ------------------------------------------------------------ */

function* mycoroutine(connection) {
    // Ensure we are live.
    var msg = yield ping()
    if (msg.ok == false) {console.log('Error ping'); return;}
    console.log('Ping successful')

    // Define a new template.
    var buf_vert = getGeometryCube();
    var templateID = [111, 108, 105];
    var cs = [4, 1, 1, 1];
    msg = yield addTemplate(templateID, cs, buf_vert);
    console.log('Added player template')

    // Spawn the just defined player template.
    var initPos = [-20, 0, 0]
    if (false) {
        // Spawn a player object.
        msg = yield spawn(templateID, initPos, [0, 0, 0], [0, 0, 0, 1], 1, 1)
        var playerID = msg.objID
        console.log('Spawned player object with objID=' + playerID);
    } else {
        // Do not spawn a dedicated player object.
        var playerID = undefined
    }

    // ----------------------------------------------------------------------
    // Rendering.
    // ----------------------------------------------------------------------
    // Compute the Aspect Ratio.
    var AR = window.innerWidth/window.innerHeight
    var FOV = 45
    
    // Create scene and camera.
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(FOV, AR, 0.1, 1000);
    
    // Initialise camera.
    camera.position.set(initPos[0], initPos[1], initPos[2]);
    camera.lookAt(new THREE.Vector3(0, 0, 0))
    camera.updateProjectionMatrix();
    
    // Add an ambient light because otherwise textures from imported Collada
    // models may not render.
    scene.add(new THREE.AmbientLight(0xcccccc));

    // Initialise the renderer and add it to the page.
    var renderer = new THREE.WebGLRenderer();
    $("#ThreeJSDiv").append(renderer.domElement)

    // Update the canvas size and aspect ratio of the camera.
    var resizeCanvas = function() {
        // Query width and height of MainContainer div.
        var w = $("#MainContainer").width()
            h = $("#MainContainer").height()

        // Compute the available height for the Canvas element:
        //
        // (95% of page height) - (content height) + (current canvas height)
        //
        // The 95% mark ensures that there is a bit of space left at
        // the bottom -- looks better.
        h = Math.floor(0.95 * window.innerHeight) - h
        h += $("#ThreeJSDiv").height()

        // Change the canvas size and update the camera.
        renderer.setSize(w, h);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
    };

    // Manually update the canvas. Afterwards, do it automatically
    // whenever the window size changes.
    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)

    // Initialise the camera controller to emulate FPS navigation.
    controls = new THREE.FlyControls(camera);
    controls.movementSpeed = 25;
    controls.rollSpeed = 10 * Math.PI / 24;
    controls.autoForward = false;
    controls.dragToLook = true;
    controls.update(1)

    // A Hashmap with all the SVs from previous objects.
    var old_SVs = {}
    var obj_cache = {}

    // Start a dedicated worker for model downloads.
    var worker = new Worker('load_model.js');
    var worker_idle = true;
    var worker_jobs = [];
    worker.onmessage = function (e) {
        // Status message.
        console.log('Received ' + Object.keys(e.data).length +
                    ' new object models from <load_model.js> Worker');

        var loader = new THREE.ColladaLoader();

        // Iterate over all downloaded models by object ID.
        for (var objID in e.data) {
            // Keys are always strings in JS, but object IDs are
            // integers in Azrael.
            objID = parseInt(objID);

            // Create an empty entry in the local object cache for the
            // new object.
            obj_cache[objID] = {};
            for (var frag_name in e.data[objID]) {
                var d = e.data[objID][frag_name];
                var scale = allSVs[objID]['sv'].scale;
                switch (d.type) {
                case 'raw':
                    var geo = compileMesh(objID, d.vert, d.uv, d.rgb, scale);

                    // Add the fragment to the local object cache and scene.
                    obj_cache[objID][frag_name] = geo;
                    scene.add(geo);
                    break;
                case 'dae':
                    console.log('Loading dae from <' + d.url + '>');
                    loader.load(
                        d.url,
                        // Function when resource is loaded
                        function (collada) {
                            console.log('Loader callback.');
                            var dae = collada.scene;
	                    dae.scale.x = dae.scale.y = dae.scale.z = scale;
	                    dae.position.x = -1;
	                    dae.updateMatrix();
    	                    scene.add(collada.scene);
                        }
                    )
                    break;
                default:
                    break;
                }
            }
        }

        // Mark the model download Worker as idle again and clear the
        // work list.
        worker_idle = true;
        worker_jobs = [];
    }

    // Query the state variables of all visible objects and update
    // their position on the screen.
    while (true) {
        // Get the SV for all objects.
        msg = yield getAllStateVariables()
        if (msg.ok == false) {console.log('Error getAllStateVariables'); return;}
        var allSVs = msg.data

        // Update the position and orientation of all objects. If an
        // object does not yet exist then create one.
        $(".progress-bar").css('width', '0%');
        var numObjects = Object.keys(allSVs).length;
        var objCnt = 0;
        for (var objID in allSVs) {
            // Convert the objID to an integer and increment the counter.
            objID = parseInt(objID);
            objCnt += 1;

            // Update text in progress bar.
            var tmp = 100 * objCnt / numObjects
                txt = objCnt + ' of ' + numObjects
            $("#PBLoading").css('width', tmp + '%').text('Loading ' + txt)

            // Skip/remove all objects with 'null' SVs. Those appear
            // whenever we asked Azrael for info about objects that do
            // not exist (anymore). Consequently, remove them from the
            // local cache as well.
            if (allSVs[objID]['sv'] == null) {
                if (objID in obj_cache) {
                    for (var fragname in obj_cache[objID]) {
                        scene.remove(obj_cache[objID][fragname]);
                    }
                    delete obj_cache[objID];
                }
                delete old_SVs[objID];
                continue;
            }

            // Remove the objects if its geometry has changed. The
            // code further down below will then think the object has
            // never existed and download it from scratch.
            if (old_SVs[objID] != undefined) {
                if (allSVs[objID]['sv'].lastChanged !=
                    old_SVs[objID]['sv'].lastChanged) {
                    for (var fragname in obj_cache[objID]) {
                        scene.remove(obj_cache[objID][fragname]);
                    }
                    delete obj_cache[objID];
                }
            }

            // Backup the SV of the current object so that we can
            // verify the checksum again in the next frame.
            old_SVs[objID] = allSVs[objID];

            // Do not render ourselves.
            if (arrayEqual(playerID, objID)) continue;

            // Update the object visuals. If the object does not yet
            // exist in our scene then earmark it for download later.
            if (obj_cache[objID] != undefined) {
                // Update the visual appearance of all fragments in objID.
                updateObjectGeometries(objID, allSVs, obj_cache);
            } else {
                // Schedule the model for download in a separate
                // thread if the Worker for that download is not
                // already busy (and potentially downloading the
                // desired models already.
                if (worker_idle == true) worker_jobs.push(objID);
            }
        }
        
        // Request the undefined models if the worker is idle.
        if ((worker_jobs.length > 0) && (worker_idle == true)) {
            // Download the meta data for the models.
            msg = yield getGeometry(worker_jobs);
            if (msg.ok == false) {
                console.log('Error getGeometry');
            } else {
                // Mark the Worker as being busy.
                worker_idle = false;

                // Send the list of objIDs for which we need the model
                // The worker also needs to know from where to
                // download them.
                worker.postMessage(
                    {'objData': msg.data,
                     'baseURL': 'http://' + window.location.host});
            }
        }

        // Remove models that do not exist anymore.
        for (var objID in obj_cache) {
            // Yes, the keys of obj_cache are integers but objID is of
            // type string -- I have no idea why.
            objID = parseInt(objID);

            // If the objID is in our cache but not in the simulation
            // then it is time to remove it.
            if (!(objID in allSVs)) {
                for (var fragname in obj_cache[objID]) {
                    scene.remove(obj_cache[objID][fragname]);
                }
                delete obj_cache[objID];
            }
        }

        // Finalise message in progress bar.
        $("#PBLoading").css('width', '100%').text('All Models Loaded')

        // The myClick attribute is set in the mouse click handler but
        // processed here to keep everything inside the co-routine.
        // The following code block will move the player object to the
        // camera position.
        if (window.myClick == true) {
            // Extract camera position.
            var pos = [0, 0, 0]
            pos[0] = camera.position.x
            pos[1] = camera.position.y
            pos[2] = camera.position.z

            // Extract camera Quaternion.
            var x = camera.quaternion.x
            var y = camera.quaternion.y
            var z = camera.quaternion.z
            var w = camera.quaternion.w

            // Obtain the view-direction of the camera. For this
            // purpose multiply the (0, 0, 1) position vector with the
            // camera Quaternion. The multiplication works via the
            // rotation matrix that corresponds to the Quaternion,
            // albeit I simplified it below since the first two
            // components of the (0, 0, 1) vector are zero anyway.
            var v1 = [1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w]
            var v2 = [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w]
            var v3 = [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]
            var view = [2*x*z + 2*y*w, 2*y*z - 2*x*w, 1 - 2*x*x - 2*y*y]
            var view_norm = Math.pow(view[0], 2) + Math.pow(view[1], 2)
            view_norm += Math.pow(view[2], 2)

            // Normalise the view vector.
            if (view_norm < 1e-6) {view = [0, 0, 0]}
            else {for (ii in view) view[ii] /= -Math.sqrt(view_norm)}

            // Put the newly spawned object a ahead of us.
            pos[0] += 2 * view[0]
            pos[1] += 2 * view[1]
            pos[2] += 2 * view[2]

            // Compute the initial velocity of the new object. It
            // moves in the view direction of the camera.
            for (ii in view) {view[ii] *= 0.2}

            // Spawn the new object at the correct position and with
            // the correct velocity and orientation.
            var templateID = [111, 108, 105];
            msg = yield spawn(templateID, pos, view, [x, y, z, w], 0.25, 20)

            // Mark the mouse event as processed.
            window.myClick = false
        }

        // Render the scene.
        renderer.render(scene, camera);

        // Update the camera position only if the mouse button is
        // pressed. This avoids accidental camera movements when you
        // use your mouse to eg switch to a different application.
        controls.update(0.01);

        // Put the player object at the camera's position.
        var pos = [0, 0, 0]
        pos[0] = camera.position.x
        pos[1] = camera.position.y
        pos[2] = camera.position.z

        if (playerID != undefined) {
            msg = yield suggestPosition(playerID, pos);
        }
    }

    console.log('All done')
}

window.onload = function() {
    // Use the ThreeJS Detector module to determine browser support for WebGL.
    var msg =
        ['<div class="container" id="MainContainer">',
         '<div class="panel panel-danger" style="max-width:400px;\
          margin-left:auto; margin-right:auto;">',
         '<div class="panel-heading">',
         '<h3 class="panel-title">WebGL Error</h3>',
         '</div>',
         '<div class="panel-body">',
         'Your Browser does not support WebGL',
         '</div>',
         '</div></div>'].join('\n')
    if (!Detector.webgl) {
        $("#Instructions").replaceWith(msg)
        return
    }

    // Create a Websocket connection.
    var connection = new WebSocket('ws://' + window.location.host + '/websocket');
    var protocol = mycoroutine(connection);

    // Error handler.
    connection.onerror = function(error) {
        console.log('Error detected: ' + error);
    }
    
    // Callback function that will handle the Websocket. This function
    // will be set in the message handler itself and is supplied by
    // the Clerk/Clacks command functions.
    this.decoder = undefined;

    // Initialise the clicked flag.
    window.myClick = false
    //window.onclick = function (event) {window.myClick = true}

    // Define callback for WS on-open.
    connection.onopen = function() {
        console.log('Established Websocket Connection')

        // Start the co-routine. It will return with two variables: 1)
        // the command for Clerk and 2) the Websocket callback
        // function that can interpret Clerk's response.
        var next = protocol.next()

        // Store the callback function and send the command to Clacks.
        this.decoder = next.value[1]
        connection.send(next.value[0])
    }

    connection.onmessage = function(msg) {
        // Decode the message with the previously installed call back
        // and pass the result to the co-routine. This will return
        // yet another command plus a callback function that can
        // interpret the response.
        var next = protocol.next(this.decoder(msg))
        if (next.done == true) {
            console.log('Finished')
            return
        }

        // Store the callback and dispatch the command.
        this.decoder = next.value[1]
        connection.send(next.value[0])
    }
}
