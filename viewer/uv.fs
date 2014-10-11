#version 330 core

// Ouput data
in vec2 UV;
out vec3 color;

uniform sampler2D gSampler;
void main()
{
  // Sample the color from a texture.
  color = texture(gSampler, UV).rgb;
}
