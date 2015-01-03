var StateVariable = function(pos, vel, orientation, scale, imass) {
    var d = {'radius': scale,
         'scale': scale,
         'imass': imass,
         'restitution': 0.9,
         'orientation': orientation,
         'position': pos,
         'velocityLin': vel,
         'velocityRot': [0, 0, 0],
         'cshape': [0, 1, 1, 1]};
    return d
}

/*
  Create a ThreeJS geometry object.
*/
function compileMesh (objID, vert, uv, scale) {
    var geo = new THREE.Geometry()

    console.log('Compiling mesh with ' + vert.length + ' vertices');

    // Apply the scaling.
    for (ii=0; ii < vert.length; ii ++) vert[ii] *= scale;

    // Determine if there are any UV coordinates available.
    var hasUV = (uv.length > 0)

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

    if (!hasUV) {
        // Assign random face colours.
        for (var i = 0; i < geo.faces.length; i++) {
            var face = geo.faces[i];
            face.color.setHex(Math.random() * 0xffffff);
        }

        // Build a new object in ThreeJS.
        var mat = new THREE.MeshBasicMaterial(
            {'vertexColors': THREE.FaceColors,
             'wireframe': false,
             'wireframeLinewidth': 3})
    } else {
        // Create a textured material.
        var fname = 'img/texture_' + objID[0] + '.jpg'
        var texture = THREE.ImageUtils.loadTexture(fname);
        var mat = new THREE.MeshBasicMaterial({
            'map': texture,
            'wireframe': false,
            'overdraw': true
        })
    }

    return new THREE.Mesh(geo, mat)
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


function setID(objID) {
    var cmd = JSON.stringify({'cmd': 'set_id', 'payload': {'objID': objID}});
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok, 'objID': parsed.payload.objID}
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

function getGeometry(objID) {
    var cmd = {'cmd': 'get_geometry', 'payload': {'objID': objID}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok,
                'vert': parsed.payload.vert,
                'UV': parsed.payload.UV,
                'RGB': parsed.payload.RGB}
    };

    return [cmd, dec]
}

function addTemplate(templateID, cs, vertices) {
    var cmd = {'cmd': 'add_template', 'payload':
               {'name': templateID, 'cs': cs, 'vert': vertices,
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
    sv.cshape = [4, 1, 1, 1]

    var payload = {'name': null, 'templateID': templateID, 'sv': sv}
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
    var cmd = {'cmd': 'get_statevar', 'payload': {'objIDs': objID}}
    cmd = JSON.stringify(cmd)
    var dec = function (msg) {
        var parsed = JSON.parse(msg.data)
        return {'ok': parsed.ok, 'sv': parsed.payload.data}
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

/* ------------------------------------------------------------
   Command flow for one frame.
 ------------------------------------------------------------ */

function* mycoroutine(connection) {
    // Ensure we are live.
    var msg = yield ping()
    if (msg.ok == false) {console.log('Error'); return;}
    console.log('Ping successful')

    // Request a new ID for the controller assigned to us.
    msg = yield setID(null)
    if (msg.ok == false) {console.log('Error'); return;}
    console.log('Controller ID: ' + msg.objID);

    // Define a new template.
    var buf_vert = getGeometryCube();
    var templateID = [111, 108, 105];
    var cs = [4, 1, 1, 1];
    msg = yield addTemplate(templateID, cs, buf_vert);
    console.log('Added player template')

    // Spawn the just defined player template.
    var initPos = [5, 0, -20]
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
    old_SVs = {}

    // Query the state variables of all visible objects and update
    // their position on the screen.
    var obj_cache = {}
    while (true) {
        // Retrieve all object IDs.
        var msg = yield getAllObjectIDs();
        if (msg.data == false) {console.log('Error'); return;}
        var objIDs = msg.objIDs

        // Get the SV for all objects.
        msg = yield getStateVariable(objIDs)
        if (msg.ok == false) {console.log('Error'); return;}
        var allSVs = msg.sv

        // Convert the 8-Byte arrays in objID to a single
        // integer. This integer will internally be used for the keys
        // in the "obj_cache map" because otherwise... strange things
        // happen.
        var objIDs_num = []
        for (var ii in objIDs) {
            var res = 0;
            for (var jj in objIDs[ii]) {
                res += Math.pow(256, jj) * objIDs[ii][jj];
            }
            objIDs_num[ii] = res;
        }

        // Update the position and orientation of all objects. If an
        // object does not yet exist then create one.
        $(".progress-bar").css('width', '0%')
        for (var ii in objIDs) {
            // Update text in progress bar.
            var tmp = 100 * (parseInt(ii) + 1) / objIDs.length
                txt = (parseInt(ii) + 1) + ' of ' + objIDs.length
            $("#PBLoading").css('width', tmp + '%').text('Loading ' + txt)

            // Skip/remove all objects with undefined SVs. Remove the
            // object from the local cache as well.
            if (allSVs[ii].sv == null) {
                if (objIDs[ii] in obj_cache) {
                    scene.remove(obj_cache[objIDs_num[ii]]);
                    delete obj_cache[objIDs_num[ii]];
                }
                delete old_SVs[ii];
                continue;
            }

            // Remove the objects if its geometry has changed. The
            // code further down below will then think the object has
            // never existed and will download it from scratch.
            if (old_SVs[ii] != undefined) {
                if (allSVs[ii].sv.checksumGeometry !=
                    old_SVs[ii].sv.checksumGeometry) {
                    scene.remove(obj_cache[objIDs_num[ii]]);
                    delete obj_cache[objIDs_num[ii]];
                }
            }

            // Backup the SV of the current object so that we can
            // verify the checksum again in the next frame.
            old_SVs[ii] = allSVs[ii];

            // Do not render ourselves.
            if (arrayEqual(playerID, objIDs[ii])) continue;

            // Download the entire object data if we do not have it
            // in the local cache.
            if (obj_cache[objIDs_num[ii]] == undefined) {
                // Get SV for current object.
                var scale = allSVs[ii].sv.scale

                // Object not yet in local cache --> fetch its geometry.
                msg = yield getGeometry(objIDs[ii]);
                if (msg.ok == false) {console.log('Error'); return;}
                var new_geo = compileMesh(objIDs[ii], msg.vert, msg.UV, scale)

                // Add the object to the cache and scene.
                obj_cache[objIDs_num[ii]] = new_geo
                scene.add(new_geo);
            }

            // Update object position.
            var sv = allSVs[ii].sv
            obj_cache[objIDs_num[ii]].position.x = sv.position[0]
            obj_cache[objIDs_num[ii]].position.y = sv.position[1]
            obj_cache[objIDs_num[ii]].position.z = sv.position[2]

            // Update object orientation.
            var q = sv.orientation
            obj_cache[objIDs_num[ii]].quaternion.x = q[0]
            obj_cache[objIDs_num[ii]].quaternion.y = q[1]
            obj_cache[objIDs_num[ii]].quaternion.z = q[2]
            obj_cache[objIDs_num[ii]].quaternion.w = q[3]

            // Apply the scale parameter.
            obj_cache[objIDs_num[ii]].scale.set(sv.scale, sv.scale, sv.scale)
        }

        // Remove models that do not exist anymore.
        for (var objID in obj_cache) {
            // Yes, the keys of obj_cache are integers but objID is of
            // type string -- I have no idea why.
            objID = parseInt(objID);

            // If the objID is in our cache but not in the simulation
            // then it is time to remove it.
            if (objIDs_num.indexOf(objID) == -1) {
                scene.remove(obj_cache[objID]);
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

        //  Update the camera position only if the mouse button is
        //  pressed. This avoids accidental camera movements when you
        //  use your mouse to eg switch to a different application.
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
