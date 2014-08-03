#version 330

// Output data
in vec4 fragmentColor;
out vec4 color;

void main()
{
  // The color is supplied by the fragment shader.
  color = fragmentColor;
}
