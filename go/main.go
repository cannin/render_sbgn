package main

// render_sbgn_go is intentionally a single-file CLI. The code is organized in
// pipeline order:
//
//   1. Parse command-line arguments.
//   2. Read SBGNML into a tiny DOM representation.
//   3. Normalize SBGN glyphs/arcs into Go structs.
//   4. Compute output bounds and coordinate transforms.
//   5. Render with tdewolff/canvas.
//   6. Export the same canvas to PNG and/or SVG.
//
// The renderer favors portability and predictable output over perfect SBGN
// coverage. New JS-baseline shape support should usually be added by extending
// jsStyleForGlyphWithColors and pathForJSShape.
import (
	"encoding/json"
	"encoding/xml"
	"errors"
	"flag"
	"fmt"
	"image/png"
	"io"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"github.com/tdewolff/canvas"
	"github.com/tdewolff/canvas/renderers/rasterizer"
	"github.com/tdewolff/canvas/renderers/svg"
)

const (
	// SBGN coordinates are treated as CSS/SVG-like pixels. canvas itself uses
	// millimeters/points for text APIs, so text sizes are converted separately.
	defaultPaddingPx = 50.0
	rendererVersion  = "0.1.0"
	fontFamilyName   = "Liberation Sans"
	arrowSize        = 8.0
	barLength        = 12.0

	// canvas text sizing uses points internally. The renderer stores font
	// sizes in SBGN pixel-like units and converts them when creating faces.
	ptPerMm = 72.0 / 25.4
)

var (
	whiteColor           = Color{R: 1.0, G: 1.0, B: 1.0, A: 1.0}
	jsNodeFillColor      = rgb(0xFF, 0xFF, 0xFF)
	jsNodeBorderColor    = rgb(0x52, 0x63, 0x6F)
	jsNodeTextColor      = rgb(0x1F, 0x29, 0x33)
	jsCompartmentBorder  = rgb(0x8A, 0xA8, 0x9B)
	jsMacromoleculeColor = rgb(0x47, 0x71, 0x8A)
	jsSimpleChemColor    = rgb(0x8B, 0x76, 0x34)
	jsComplexColor       = rgb(0x6C, 0x5D, 0x82)
	jsProcessColor       = rgb(0x57, 0x5F, 0x67)
	jsSubmapColor        = rgb(0x47, 0x7B, 0x5A)
	jsPhenotypeColor     = rgb(0x9A, 0x5B, 0x55)
	jsSourceSinkColor    = rgb(0x1D, 0x23, 0x29)
	jsGlyphColorBorder   = rgb(0x16, 0x19, 0x1F)
	jsEdgeColor          = rgb(0x61, 0x71, 0x7D)
)

type Color struct {
	R float64
	G float64
	B float64
	A float64
}

// Point is a coordinate in the renderer's current coordinate space. Parsed SBGN
// points are logical diagram coordinates; rendered points are output pixels.
type Point struct {
	X float64
	Y float64
}

type BBox struct {
	X float64
	Y float64
	W float64
	H float64
}

type PixelRect struct {
	X0     float64
	Y0     float64
	Width  float64
	Height float64
	Center Point
}

type GlyphColorType string

const (
	glyphColorTypeLabel GlyphColorType = "label"
	glyphColorTypeID    GlyphColorType = "id"
)

// Glyph is the normalized representation of an SBGN <glyph>. Child glyphs are
// flattened into the same slice and linked by ParentID; this makes z-order and
// auxiliary rendering easier to control than walking the XML tree repeatedly.
type Glyph struct {
	ID            string
	ParentID      string
	ClassName     string
	BBox          *BBox
	Label         string
	Ports         []Port
	HasClone      bool
	StateValue    string
	StateVariable string
	Orientation   string
}

type Port struct {
	ID string
	Point
}

// Arc stores the visible polyline points of an SBGN <arc>. Source/target are
// kept as raw ids because SBGN arcs can refer to glyph ports as "glyph.port".
type Arc struct {
	ID        string
	ClassName string
	Source    string
	Target    string
	Points    []Point
}

type Bounds struct {
	MinX float64
	MaxX float64
	MinY float64
	MaxY float64
}

type Transform struct {
	MinX    float64
	MinY    float64
	ScaleX  float64
	ScaleY  float64
	OffsetX float64
	OffsetY float64
}

type OutputFormat string

const (
	outputPNG OutputFormat = "png"
	outputSVG OutputFormat = "svg"
)

type TagOrientation int

const (
	tagLeft TagOrientation = iota
	tagRight
)

type RenderStyle struct {
	FontSize          *float64
	FontFamily        string
	FontColor         *Color
	StrokeColor       *Color
	StrokeWidth       *float64
	FillColor         *Color
	BackgroundOpacity *float64
}

// RenderInfo holds optional <renderInformation> styling. Styles with an empty
// idList become defaults; id-specific styles override those defaults.
type RenderInfo struct {
	BackgroundColor *Color
	DefaultStyle    *RenderStyle
	Styles          map[string]RenderStyle
	Colors          map[string]Color
}

type ManifestRecord struct {
	DiagramID       string            `json:"diagram_id"`
	CoordinateSpace string            `json:"coordinate_space"`
	Canvas          ManifestCanvas    `json:"canvas"`
	Elements        []ManifestElement `json:"elements"`
}

type ManifestCanvas struct {
	MinX   float64 `json:"min_x"`
	MinY   float64 `json:"min_y"`
	MaxX   float64 `json:"max_x"`
	MaxY   float64 `json:"max_y"`
	Width  float64 `json:"width"`
	Height float64 `json:"height"`
}

type ManifestElement struct {
	ID      string   `json:"id"`
	OwnerID string   `json:"owner_id"`
	Kind    string   `json:"kind"`
	Type    string   `json:"type"`
	Class   string   `json:"class"`
	X1      *float64 `json:"x1"`
	Y1      *float64 `json:"y1"`
	X2      *float64 `json:"x2"`
	Y2      *float64 `json:"y2"`
	CX      *float64 `json:"cx"`
	CY      *float64 `json:"cy"`
	Width   *float64 `json:"width"`
	Height  *float64 `json:"height"`
	Text    string   `json:"text"`
	Marker  string   `json:"marker"`
	Source  string   `json:"source"`
	Target  string   `json:"target"`
	FontPx  *float64 `json:"font_px"`
}

type jsGlyphStyle struct {
	Shape       string
	Label       string
	FontPx      float64
	LabelValign string
	Fill        *Color
	Border      Color
	BorderWidth float64
	TextColor   Color
	Dashed      bool
}

type ClassStyle struct {
	Fill        string   `json:"fill"`
	FillOpacity *float64 `json:"fill_opacity"`
	Opacity     *float64 `json:"opacity"`
	Border      string   `json:"border"`
}

type StyleConfig struct {
	BackgroundColor string                `json:"background_color"`
	TextColor       string                `json:"text_color"`
	EdgeColor       string                `json:"edge_color"`
	Styles          map[string]ClassStyle `json:"styles"`
}

// xmlElement is a deliberately small DOM node. The renderer only needs local
// names, attributes, and element children, so it avoids a heavier XML model.
type xmlElement struct {
	Name     string
	Attrs    map[string]string
	Children []*xmlElement
}

type renderer struct {
	ctx        *canvas.Context
	fontFamily *canvas.FontFamily
}

// main runs the command-line entry point and reports any error to stderr.
func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// run dispatches the top-level CLI command.
// Parameters: args contains the command and its arguments, excluding argv[0].
func run(args []string) error {
	if len(args) == 0 {
		return errors.New(usage())
	}
	switch args[0] {
	case "draw_sbgnml":
		return runDrawSbgnml(args[1:])
	case "-v", "--version", "version":
		fmt.Println(rendererVersion)
		return nil
	case "-h", "--help", "help":
		fmt.Print(usage())
		return nil
	default:
		return fmt.Errorf("unknown command %q\n%s", args[0], usage())
	}
}

// usage returns the top-level help text.
func usage() string {
	return `render_sbgn_go renders SBGNML diagrams to PNG and SVG.

Usage:
  render_sbgn_go draw_sbgnml --input-path FILE [-o FILE.png|FILE.svg] [--format png,svg] [--padding 50] [--width PX] [--height PX] [--clone-markers true|false] [--glyph-colors JSON | --glyph-colors-json-file FILE | --style-json-file FILE] [--glyph-color-type label|id] [--auto-contrast-text true|false] [--generate-render-test-manifest]
`
}

// runDrawSbgnml parses flags for the draw_sbgnml command and starts rendering.
// Parameters: args contains draw_sbgnml flags and values after the command name.
func runDrawSbgnml(args []string) error {
	var input string
	var output string
	var format string
	var padding float64
	var width float64
	var height float64
	var cloneMarkers bool
	var autoContrastText bool
	var generateRenderTestManifest bool
	var glyphColorsJSON string
	var glyphColorTypeRaw string
	var glyphColorsJSONFile string
	var styleJSONFile string

	fs := flag.NewFlagSet("draw_sbgnml", flag.ContinueOnError)
	fs.StringVar(&input, "input-path", "", "SBGNML input file")
	fs.StringVar(&input, "input_path", "", "SBGNML input file")
	fs.StringVar(&input, "input", "", "SBGNML input file")
	fs.StringVar(&input, "i", "", "SBGNML input file")
	fs.StringVar(&output, "output-path", "", "output PNG or SVG path")
	fs.StringVar(&output, "output_path", "", "output PNG or SVG path")
	fs.StringVar(&output, "output", "", "output PNG or SVG path")
	fs.StringVar(&output, "o", "", "output base path")
	fs.StringVar(&format, "format", "png,svg", "comma-separated output formats")
	fs.StringVar(&format, "f", "png,svg", "comma-separated output formats")
	fs.Float64Var(&padding, "padding", defaultPaddingPx, "padding in output units")
	fs.Float64Var(&padding, "p", defaultPaddingPx, "padding in output units")
	fs.Float64Var(&width, "width", 0, "output width in pixels")
	fs.Float64Var(&height, "height", 0, "output height in pixels")
	fs.BoolVar(&cloneMarkers, "clone-markers", true, "draw clone markers")
	fs.BoolVar(&cloneMarkers, "clone_markers", true, "draw clone markers")
	fs.BoolVar(&autoContrastText, "auto-contrast-text", true, "auto-contrast glyph text against custom fill colors")
	fs.BoolVar(&autoContrastText, "auto_contrast_text", true, "auto-contrast glyph text against custom fill colors")
	fs.BoolVar(&generateRenderTestManifest, "generate-render-test-manifest", false, "write render-test manifest JSON instead of images")
	fs.BoolVar(&generateRenderTestManifest, "generate_render_test_manifest", false, "write render-test manifest JSON instead of images")
	fs.StringVar(&glyphColorsJSON, "glyph-colors", "{}", "JSON object mapping glyph labels or ids to CSS hex colors")
	fs.StringVar(&glyphColorsJSON, "glyph_colors", "{}", "JSON object mapping glyph labels or ids to CSS hex colors")
	fs.StringVar(&glyphColorTypeRaw, "glyph-color-type", "label", "glyph color key type: label or id")
	fs.StringVar(&glyphColorTypeRaw, "glyph_color_type", "label", "glyph color key type: label or id")
	fs.StringVar(&glyphColorsJSONFile, "glyph-colors-json-file", "", "JSON file mapping glyph labels or ids to colors")
	fs.StringVar(&glyphColorsJSONFile, "glyph_colors_json_file", "", "JSON file mapping glyph labels or ids to colors")
	fs.StringVar(&styleJSONFile, "style-json-file", "", "JSON class style file")
	fs.StringVar(&styleJSONFile, "style_json_file", "", "JSON class style file")
	if err := fs.Parse(args); err != nil {
		return err
	}
	glyphColorsProvided := false
	fs.Visit(func(flag *flag.Flag) {
		switch flag.Name {
		case "glyph-colors", "glyph_colors":
			glyphColorsProvided = true
		}
	})
	if input == "" {
		return errors.New("--input-path is required")
	}

	outputBase := output
	if outputBase == "" {
		outputBase = input
	}
	glyphColors, err := parseGlyphColors(glyphColorsJSON)
	if err != nil {
		return err
	}
	colorInputs := 0
	if glyphColorsProvided {
		colorInputs++
	}
	if glyphColorsJSONFile != "" {
		colorInputs++
	}
	if styleJSONFile != "" {
		colorInputs++
	}
	if colorInputs > 1 {
		return errors.New("use only one of --glyph-colors, --glyph-colors-json-file, or --style-json-file")
	}
	if glyphColorsJSONFile != "" {
		glyphColors, err = parseGlyphColorsFile(glyphColorsJSONFile)
		if err != nil {
			return err
		}
	}
	var styleConfig *StyleConfig
	if styleJSONFile != "" {
		styleConfig, err = parseStyleConfigFile(styleJSONFile)
		if err != nil {
			return err
		}
	}
	glyphColorType, err := parseGlyphColorType(glyphColorTypeRaw)
	if err != nil {
		return err
	}
	if generateRenderTestManifest {
		manifestOutput := output
		if manifestOutput == "" {
			manifestOutput = outputPathForManifest(input)
		}
		return writeRenderTestManifest(
			input,
			manifestOutput,
			padding,
			width,
			height,
			glyphColors,
			glyphColorType,
			autoContrastText,
			styleConfig,
		)
	}
	formats, err := outputFormats(output, format)
	if err != nil {
		return err
	}
	return drawSbgnml(input, outputBase, formats, padding, cloneMarkers, glyphColors, glyphColorType, autoContrastText, styleConfig, width, height)
}

// parseGlyphColors decodes a label/id-to-color JSON object from the CLI.
// Parameters: raw is JSON supplied by --glyph-colors.
func parseGlyphColors(raw string) (map[string]string, error) {
	glyphColors := map[string]string{}
	if strings.TrimSpace(raw) == "" {
		return glyphColors, nil
	}
	if err := json.Unmarshal([]byte(raw), &glyphColors); err != nil {
		return nil, fmt.Errorf("invalid --glyph-colors: %w", err)
	}
	return glyphColors, nil
}

func parseGlyphColorsFile(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var wrapper struct {
		GlyphColors map[string]string `json:"glyph_colors"`
	}
	if err := json.Unmarshal(data, &wrapper); err == nil && wrapper.GlyphColors != nil {
		return wrapper.GlyphColors, nil
	}
	var colors map[string]string
	if err := json.Unmarshal(data, &colors); err != nil {
		return nil, fmt.Errorf("invalid glyph colors JSON file: %w", err)
	}
	return colors, nil
}

func parseStyleConfigFile(path string) (*StyleConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var styleConfig StyleConfig
	if err := json.Unmarshal(data, &styleConfig); err != nil {
		return nil, fmt.Errorf("invalid style JSON file: %w", err)
	}
	if styleConfig.Styles == nil {
		return nil, errors.New("style JSON file must contain a styles object")
	}
	return &styleConfig, nil
}

func parseGlyphColorType(raw string) (GlyphColorType, error) {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "label":
		return glyphColorTypeLabel, nil
	case "id":
		return glyphColorTypeID, nil
	default:
		return "", fmt.Errorf("invalid --glyph-color-type %q: use label or id", raw)
	}
}

// rgb converts integer 8-bit RGB channels to a fully opaque Color.
// Parameters: r, g, and b are red, green, and blue channel values in 0..255.
func rgb(r int, g int, b int) Color {
	return Color{
		R: float64(r) / 255.0,
		G: float64(g) / 255.0,
		B: float64(b) / 255.0,
		A: 1.0,
	}
}

// canvasColor converts a Color to the representation expected by canvas.
// Parameters: color is the renderer color to convert; transparent colors return nil.
func (color Color) canvasColor() interface{} {
	if color.A <= 0.0 {
		return nil
	}
	return canvas.RGBA(color.R, color.G, color.B, color.A)
}

// mapPoint maps one logical SBGN point into output coordinates.
// Parameters: t is the transform; x and y are logical SBGN coordinates.
func (t Transform) mapPoint(x float64, y float64) Point {
	return Point{
		X: t.OffsetX + (x-t.MinX)*t.ScaleX,
		Y: t.OffsetY + (y-t.MinY)*t.ScaleY,
	}
}

// scaleScalar scales a length using the smaller transform axis to preserve marker proportions.
// Parameters: t is the transform; value is the logical scalar length.
func (t Transform) scaleScalar(value float64) float64 {
	return value * math.Min(t.ScaleX, t.ScaleY)
}

// drawSbgnml parses an SBGNML file, renders it once, and writes requested outputs.
// Parameters: input is the SBGNML path; outputBase is the base output path; formats lists PNG/SVG targets; padding expands bounds; showCloneMarkers toggles clone overlays.
func drawSbgnml(input string, outputBase string, formats []OutputFormat, padding float64, showCloneMarkers bool, glyphColors map[string]string, glyphColorType GlyphColorType, autoContrastText bool, styleConfig *StyleConfig, outputWidth float64, outputHeight float64) error {
	root, err := readXMLFile(input)
	if err != nil {
		return err
	}
	renderInfo := parseRenderInformation(root)
	if styleConfig != nil {
		renderInfo.BackgroundColor = styleConfig.backgroundColor()
	}
	glyphs, arcs, bounds, err := parseSBGN(root)
	if err != nil {
		return err
	}
	tagOrientations := computeTagOrientations(glyphs, arcs)
	transform, width, height := transformWithPadding(bounds, padding, outputWidth, outputHeight)

	// Build once, then serialize to each requested output. This keeps PNG/SVG
	// geometry identical because both outputs come from the same canvas scene.
	picture, err := buildCanvas(width, height, renderInfo.BackgroundColor, &transform, glyphs, arcs, renderInfo, tagOrientations, showCloneMarkers, glyphColors, glyphColorType, autoContrastText, styleConfig)
	if err != nil {
		return err
	}

	for _, format := range formats {
		outputPath := outputPathForFormat(outputBase, format)
		if err := writeCanvas(outputPath, format, picture); err != nil {
			return err
		}
	}
	return nil
}

// writeRenderTestManifest emits the primitive geometry manifest used by rendering_test.
// Parameters: input is the SBGNML path; outputPath is the destination JSON file.
func writeRenderTestManifest(input string, outputPath string, padding float64, outputWidth float64, outputHeight float64, glyphColors map[string]string, glyphColorType GlyphColorType, autoContrastText bool, styleConfig *StyleConfig) error {
	root, err := readXMLFile(input)
	if err != nil {
		return err
	}
	glyphs, arcs, bounds, err := parseSBGN(root)
	if err != nil {
		return err
	}
	manifest := buildRenderTestManifest(filepath.Base(input), glyphs, arcs, bounds, glyphColors, glyphColorType, autoContrastText, styleConfig)
	if outputWidth > 0 && outputHeight > 0 {
		manifest = transformManifestToRenderedPixels(manifest, bounds, padding, outputWidth, outputHeight)
	}

	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil && filepath.Dir(outputPath) != "." {
		return err
	}
	file, err := os.Create(outputPath)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(manifest)
}

// buildRenderTestManifest converts parsed renderer data into JS-comparable primitives.
// Parameters: diagramID is the source filename; glyphs/arcs/bounds are parsed SBGN data.
func buildRenderTestManifest(diagramID string, glyphs []Glyph, arcs []Arc, bounds Bounds, glyphColors map[string]string, glyphColorType GlyphColorType, autoContrastText bool, styleConfig *StyleConfig) ManifestRecord {
	glyphByID := map[string]*Glyph{}
	portParentByID := map[string]string{}
	for index := range glyphs {
		glyph := &glyphs[index]
		if _, exists := glyphByID[glyph.ID]; exists {
			continue
		}
		glyphByID[glyph.ID] = glyph
		for _, port := range glyph.Ports {
			if port.ID != "" {
				portParentByID[port.ID] = glyph.ID
			}
		}
	}

	elements := []ManifestElement{}
	emittedLabels := map[string]bool{}
	addElement := func(element ManifestElement) {
		elements = append(elements, element)
	}

	minX, minY := math.Inf(1), math.Inf(1)
	maxX, maxY := math.Inf(-1), math.Inf(-1)
	includeRect := func(rect PixelRect) {
		minX = math.Min(minX, rect.X0)
		minY = math.Min(minY, rect.Y0)
		maxX = math.Max(maxX, rect.X0+rect.Width)
		maxY = math.Max(maxY, rect.Y0+rect.Height)
	}

	for index := range glyphs {
		glyph := &glyphs[index]
		if glyph.BBox == nil || isJSHiddenGlyphClass(glyph.ClassName) {
			continue
		}
		if glyphByID[glyph.ID] != glyph {
			addManifestLabelIfNeeded(glyph, emittedLabels, addElement, glyphColors, glyphColorType, autoContrastText, styleConfig)
			continue
		}
		rect := manifestRect(*glyph.BBox)
		style := jsStyleForGlyphWithColors(glyph, glyphColors, glyphColorType, autoContrastText, styleConfig)
		includeRect(rect)
		addElement(ManifestElement{
			ID: glyph.ID + "::shape", OwnerID: glyph.ID, Kind: "node_shape", Type: style.Shape, Class: glyph.ClassName,
			X1: floatPtr(rect.X0), Y1: floatPtr(rect.Y0), X2: floatPtr(rect.X0 + rect.Width), Y2: floatPtr(rect.Y0 + rect.Height),
			CX: floatPtr(rect.Center.X), CY: floatPtr(rect.Center.Y), Width: floatPtr(rect.Width), Height: floatPtr(rect.Height),
		})
		if strings.TrimSpace(style.Label) != "" {
			labelY := rect.Center.Y
			if style.LabelValign == "top" {
				labelY = rect.X0
				labelY = rect.Y0 + math.Max(8.0, style.FontPx)
			}
			addElement(ManifestElement{
				ID: glyph.ID + "::label", OwnerID: glyph.ID, Kind: "label", Type: "text", Class: glyph.ClassName,
				CX: floatPtr(rect.Center.X), CY: floatPtr(labelY), Width: floatPtr(math.Max(1.0, rect.Width-8.0)), Height: floatPtr(math.Max(1.0, rect.Height-8.0)),
				Text: style.Label,
			})
			emittedLabels[glyph.ID+"::label"] = true
		}
	}

	for _, arc := range arcs {
		points, sourceID, targetID, ok := jsArcPoints(arc, glyphByID, portParentByID)
		if !ok {
			continue
		}
		marker := jsArcMarker(arc.ClassName)
		addElement(ManifestElement{
			ID: arc.ID + "::line", OwnerID: arc.ID, Kind: "edge_line", Type: "line", Class: arc.ClassName,
			X1: floatPtr(points[0].X), Y1: floatPtr(points[0].Y), X2: floatPtr(points[1].X), Y2: floatPtr(points[1].Y),
			CX: floatPtr((points[0].X + points[1].X) / 2.0), CY: floatPtr((points[0].Y + points[1].Y) / 2.0),
			Marker: marker, Source: sourceID, Target: targetID,
		})
		if marker != "none" {
			addElement(ManifestElement{
				ID: arc.ID + "::marker", OwnerID: arc.ID, Kind: "edge_marker", Type: marker, Class: arc.ClassName,
				CX: floatPtr(points[1].X), CY: floatPtr(points[1].Y), Marker: marker, Source: sourceID, Target: targetID,
			})
		}
	}

	if !isFinite(minX) || !isFinite(minY) || !isFinite(maxX) || !isFinite(maxY) {
		minX, minY, maxX, maxY = bounds.MinX, bounds.MinY, bounds.MaxX, bounds.MaxY
	}
	return ManifestRecord{
		DiagramID:       diagramID,
		CoordinateSpace: "source",
		Canvas: ManifestCanvas{
			MinX: minX, MinY: minY, MaxX: maxX, MaxY: maxY,
			Width: math.Max(0.0, maxX-minX), Height: math.Max(0.0, maxY-minY),
		},
		Elements: elements,
	}
}

// transformManifestToRenderedPixels converts source-coordinate manifest geometry to the renderer's final pixel coordinates.
// Parameters: manifest is the source manifest; bounds, padding, and output dimensions define the image transform.
func transformManifestToRenderedPixels(manifest ManifestRecord, bounds Bounds, padding float64, outputWidth float64, outputHeight float64) ManifestRecord {
	transform, width, height := transformWithPadding(bounds, padding, outputWidth, outputHeight)
	scale := math.Min(math.Abs(transform.ScaleX), math.Abs(transform.ScaleY))
	mapX := func(value *float64) *float64 {
		if value == nil {
			return nil
		}
		mapped := transform.mapPoint(*value, 0).X
		return &mapped
	}
	mapY := func(value *float64) *float64 {
		if value == nil {
			return nil
		}
		mapped := transform.mapPoint(0, *value).Y
		return &mapped
	}

	for index := range manifest.Elements {
		element := &manifest.Elements[index]
		element.X1 = mapX(element.X1)
		element.X2 = mapX(element.X2)
		element.CX = mapX(element.CX)
		element.Y1 = mapY(element.Y1)
		element.Y2 = mapY(element.Y2)
		element.CY = mapY(element.CY)
		if element.Width != nil {
			scaled := *element.Width * scale
			element.Width = &scaled
		}
		if element.Height != nil {
			scaled := *element.Height * scale
			element.Height = &scaled
		}
	}

	manifest.CoordinateSpace = "rendered_pixel"
	manifest.Canvas = ManifestCanvas{MinX: 0, MinY: 0, MaxX: width, MaxY: height, Width: width, Height: height}
	return manifest
}

// manifestRect converts an SBGN bbox to the manifest rectangle coordinate model.
// Parameters: bbox is a parsed glyph bounding box.
func manifestRect(bbox BBox) PixelRect {
	return PixelRect{
		X0:     bbox.X,
		Y0:     bbox.Y,
		Width:  bbox.W,
		Height: bbox.H,
		Center: Point{X: bbox.X + bbox.W/2.0, Y: bbox.Y + bbox.H/2.0},
	}
}

// isJSHiddenGlyphClass reports whether Cytoscape omits a glyph as a standalone node.
// Parameters: className is the SBGN glyph class.
func isJSHiddenGlyphClass(className string) bool {
	return className == "unit of information" || className == "state variable"
}

// jsStyleForGlyph returns the JS baseline primitive shape and label behavior.
// Parameters: glyph is the parsed SBGN glyph.
func jsStyleForGlyph(glyph *Glyph, glyphColors map[string]string) jsGlyphStyle {
	return jsStyleForGlyphWithColors(glyph, glyphColors, glyphColorTypeLabel, true, nil)
}

func jsStyleForGlyphWithColors(glyph *Glyph, glyphColors map[string]string, glyphColorType GlyphColorType, autoContrastText bool, styleConfig *StyleConfig) jsGlyphStyle {
	className := glyph.ClassName
	label := strings.TrimSpace(glyph.Label)
	if className == "submap" {
		label = glyph.Label
	}
	style := jsGlyphStyle{
		Shape:       "rounded_rectangle",
		Label:       label,
		FontPx:      10.0,
		LabelValign: "center",
		Fill:        ptrColor(jsNodeFillColor),
		Border:      jsNodeBorderColor,
		BorderWidth: 1.4,
		TextColor:   jsNodeTextColor,
	}
	if className == "compartment" {
		style.Fill = nil
		style.Border = jsCompartmentBorder
		style.BorderWidth = 2.0
		style.FontPx = 12.0
		style.LabelValign = "top"
		style.Dashed = true
	}
	if strings.Contains(className, "macromolecule") {
		style.Border = jsMacromoleculeColor
	}
	if strings.Contains(className, "simple chemical") {
		style.Shape = "ellipse"
		style.Border = jsSimpleChemColor
	}
	if strings.Contains(className, "complex") {
		style.Border = jsComplexColor
		style.BorderWidth = 2.0
	}
	if strings.Contains(className, "process") || className == "association" || className == "dissociation" {
		style.Shape = "rectangle"
		style.Border = jsProcessColor
		style.Label = ""
	}
	if className == "submap" {
		style.Border = jsSubmapColor
		style.BorderWidth = 2.0
	}
	if className == "phenotype" {
		style.Shape = "hexagon"
		style.Border = jsPhenotypeColor
	}
	if className == "source and sink" {
		style.Shape = "ellipse"
		style.Border = jsSourceSinkColor
		style.Label = ""
	}
	if classStyle, ok := styleConfig.styleForClass(className); ok {
		if color, ok := parseHexColor(classStyle.Fill); ok {
			if classStyle.FillOpacity != nil {
				color.A = math.Max(0.0, math.Min(1.0, *classStyle.FillOpacity))
			} else if classStyle.Opacity != nil {
				color.A = math.Max(0.0, math.Min(1.0, *classStyle.Opacity))
			}
			style.Fill = ptrColor(color)
		}
		if color, ok := parseHexColor(classStyle.Border); ok {
			style.Border = color
		}
	}
	if textColor, ok := styleConfig.textColor(); ok {
		style.TextColor = textColor
	}
	colorKey := strings.TrimSpace(glyph.Label)
	if glyphColorType == glyphColorTypeID {
		colorKey = glyph.ID
	}
	if fill, ok := glyphColors[colorKey]; ok {
		if color, ok := parseHexColor(fill); ok {
			style.Fill = ptrColor(color)
			style.Border = jsGlyphColorBorder
			style.BorderWidth = 2.4
			if autoContrastText {
				style.TextColor = jsTextColorForFill(color)
			}
		}
	}
	return style
}

// jsTextColorForFill chooses the JS text color for a custom-filled node.
// Parameters: fill is the node fill color.
func jsTextColorForFill(fill Color) Color {
	linear := func(channel float64) float64 {
		if channel <= 0.03928 {
			return channel / 12.92
		}
		return math.Pow((channel+0.055)/1.055, 2.4)
	}
	luminance := 0.2126*linear(fill.R) + 0.7152*linear(fill.G) + 0.0722*linear(fill.B)
	if luminance < 0.45 {
		return whiteColor
	}
	return jsNodeTextColor
}

// addManifestLabelIfNeeded emits a duplicate-id glyph label when JS exposes one.
// Parameters: glyph is the duplicate glyph; emittedLabels tracks existing label ids; addElement appends manifest elements.
func addManifestLabelIfNeeded(glyph *Glyph, emittedLabels map[string]bool, addElement func(ManifestElement), glyphColors map[string]string, glyphColorType GlyphColorType, autoContrastText bool, styleConfig *StyleConfig) {
	if glyph.BBox == nil {
		return
	}
	style := jsStyleForGlyphWithColors(glyph, glyphColors, glyphColorType, autoContrastText, styleConfig)
	if strings.TrimSpace(style.Label) == "" {
		return
	}
	labelID := glyph.ID + "::label"
	if emittedLabels[labelID] {
		return
	}
	rect := manifestRect(*glyph.BBox)
	labelY := rect.Center.Y
	if style.LabelValign == "top" {
		labelY = rect.Y0 + math.Max(8.0, style.FontPx)
	}
	addElement(ManifestElement{
		ID: labelID, OwnerID: glyph.ID, Kind: "label", Type: "text", Class: glyph.ClassName,
		CX: floatPtr(rect.Center.X), CY: floatPtr(labelY), Width: floatPtr(math.Max(1.0, rect.Width-8.0)), Height: floatPtr(math.Max(1.0, rect.Height-8.0)),
		Text: style.Label,
	})
	emittedLabels[labelID] = true
}

// jsArcPoints resolves arc endpoints to JS-style node-boundary points.
// Parameters: arc is the parsed SBGN arc; glyphByID and portParentByID are lookup maps.
func jsArcPoints(arc Arc, glyphByID map[string]*Glyph, portParentByID map[string]string) ([2]Point, string, string, bool) {
	sourceID := jsEndpointGlyphID(arc.Source, portParentByID)
	targetID := jsEndpointGlyphID(arc.Target, portParentByID)
	sourceGlyph := glyphByID[sourceID]
	targetGlyph := glyphByID[targetID]
	if sourceGlyph == nil || targetGlyph == nil || sourceGlyph.BBox == nil || targetGlyph.BBox == nil {
		return [2]Point{}, "", "", false
	}
	if isJSHiddenGlyphClass(sourceGlyph.ClassName) || isJSHiddenGlyphClass(targetGlyph.ClassName) {
		return [2]Point{}, "", "", false
	}
	sourceRect := manifestRect(*sourceGlyph.BBox)
	targetRect := manifestRect(*targetGlyph.BBox)
	start := jsNodeBoundaryPoint(sourceGlyph, targetRect.Center)
	end := jsNodeBoundaryPoint(targetGlyph, sourceRect.Center)
	return [2]Point{start, end}, sourceID, targetID, true
}

// jsEndpointGlyphID maps a port reference back to its owning glyph for JS topology.
// Parameters: reference is an arc endpoint id; portParentByID maps port ids to glyph ids.
func jsEndpointGlyphID(reference string, portParentByID map[string]string) string {
	if parentID, ok := portParentByID[reference]; ok {
		return parentID
	}
	return reference
}

// jsNodeBoundaryPoint intersects a center-to-center segment with the JS node shape.
// Parameters: glyph is the endpoint glyph; other is the opposite glyph center.
func jsNodeBoundaryPoint(glyph *Glyph, other Point) Point {
	if jsStyleForGlyph(glyph, nil).Shape == "ellipse" {
		return ellipseBoundaryPoint(*glyph.BBox, other)
	}
	return rectBoundaryPoint(*glyph.BBox, other)
}

// rectBoundaryPoint intersects a line from another point with a rectangle.
// Parameters: bbox is the target rectangle; other is the opposite point.
func rectBoundaryPoint(bbox BBox, other Point) Point {
	rect := manifestRect(bbox)
	dx := rect.Center.X - other.X
	dy := rect.Center.Y - other.Y
	if math.Hypot(dx, dy) <= 1e-6 {
		return rect.Center
	}
	candidates := []float64{}
	if math.Abs(dx) > 1e-6 {
		candidates = append(candidates, (rect.X0-other.X)/dx, (rect.X0+rect.Width-other.X)/dx)
	}
	if math.Abs(dy) > 1e-6 {
		candidates = append(candidates, (rect.Y0-other.Y)/dy, (rect.Y0+rect.Height-other.Y)/dy)
	}
	sort.Float64s(candidates)
	for _, scale := range candidates {
		if scale < 0.0 || scale > 1.0 {
			continue
		}
		x := other.X + dx*scale
		y := other.Y + dy*scale
		if x >= rect.X0-1e-6 && x <= rect.X0+rect.Width+1e-6 && y >= rect.Y0-1e-6 && y <= rect.Y0+rect.Height+1e-6 {
			return Point{X: x, Y: y}
		}
	}
	return rect.Center
}

// ellipseBoundaryPoint intersects a line from the node center with an ellipse.
// Parameters: bbox is the target ellipse bounds; other is the opposite point.
func ellipseBoundaryPoint(bbox BBox, other Point) Point {
	rect := manifestRect(bbox)
	dx := other.X - rect.Center.X
	dy := other.Y - rect.Center.Y
	if math.Hypot(dx, dy) <= 1e-6 {
		return rect.Center
	}
	rx := rect.Width / 2.0
	ry := rect.Height / 2.0
	scale := 1.0 / math.Sqrt(math.Pow(dx/rx, 2)+math.Pow(dy/ry, 2))
	return Point{X: rect.Center.X + dx*scale, Y: rect.Center.Y + dy*scale}
}

// jsArcMarker maps SBGN arc classes to the JS baseline marker primitive.
// Parameters: className is the SBGN arc class.
func jsArcMarker(className string) string {
	switch className {
	case "consumption":
		return "none"
	case "inhibition":
		return "tee"
	case "catalysis":
		return "circle"
	default:
		return "triangle"
	}
}

// floatPtr returns a pointer to value for JSON fields that may be null.
// Parameters: value is the coordinate to reference.
func floatPtr(value float64) *float64 {
	return &value
}

// isFinite reports whether a float is neither NaN nor infinite.
// Parameters: value is the float to test.
func isFinite(value float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0)
}

// buildCanvas creates a canvas scene and draws all glyphs and arcs into it.
// Parameters: width/height define output size; background is optional page color; transform maps SBGN coordinates; glyphs/arcs are normalized diagram data; renderInfo holds styles; tagOrientations contains inferred tag notches; showCloneMarkers toggles clone overlays.
func buildCanvas(width float64, height float64, background *Color, transform *Transform, glyphs []Glyph, arcs []Arc, renderInfo RenderInfo, tagOrientations map[string]TagOrientation, showCloneMarkers bool, glyphColors map[string]string, glyphColorType GlyphColorType, autoContrastText bool, styleConfig *StyleConfig) (*canvas.Canvas, error) {
	picture := canvas.New(width, height)
	ctx := canvas.NewContext(picture)
	// CartesianIV makes the canvas coordinate system match SBGN/SVG: origin at
	// top-left, x to the right, y downward.
	ctx.SetCoordSystem(canvas.CartesianIV)

	bg := whiteColor
	if background != nil && background.A > 0.0 {
		bg = *background
	}
	ctx.SetFill(bg.canvasColor())
	ctx.SetStroke(nil)
	ctx.DrawPath(0, 0, canvas.Rectangle(width, height))

	fontFamily, err := loadFontFamily(fontFamilyName)
	if err != nil {
		return nil, err
	}
	r := renderer{
		ctx:        ctx,
		fontFamily: fontFamily,
	}
	if err := r.renderSBGNML(transform, glyphs, arcs, renderInfo, tagOrientations, showCloneMarkers, glyphColors, glyphColorType, autoContrastText, styleConfig); err != nil {
		return nil, err
	}
	return picture, nil
}

// loadFontFamily loads a practical sans-serif font family for canvas text rendering.
// Parameters: name is the preferred family name before fallback candidates are tried.
func loadFontFamily(name string) (*canvas.FontFamily, error) {
	family := canvas.NewFontFamily(name)
	// Keep a practical sans-serif fallback list for hosts with different font
	// packages. SVG output should also preserve a CSS fallback stack when code
	// is changed to write text attributes directly.
	candidates := []string{name, "Liberation Sans", "DejaVu Sans", "Arial", "Helvetica", "sans-serif"}
	var lastErr error
	for _, candidate := range candidates {
		if err := family.LoadSystemFont(candidate, canvas.FontRegular); err == nil {
			return family, nil
		} else {
			lastErr = err
		}
	}
	return nil, fmt.Errorf("failed to load a system font for SBGN labels: %w", lastErr)
}

// writeCanvas serializes a rendered canvas to PNG or SVG.
// Parameters: outputPath is the destination file; format selects encoder; picture is the rendered canvas.
func writeCanvas(outputPath string, format OutputFormat, picture *canvas.Canvas) error {
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil && filepath.Dir(outputPath) != "." {
		return err
	}
	file, err := os.Create(outputPath)
	if err != nil {
		return err
	}
	defer file.Close()

	switch format {
	case outputPNG:
		img := rasterizer.Draw(picture, canvas.DPMM(1.0), canvas.DefaultColorSpace)
		return png.Encode(file, img)
	case outputSVG:
		options := svg.DefaultOptions
		options.SizeUnits = "px"
		writer := svg.New(file, picture.W, picture.H, &options)
		picture.RenderTo(writer)
		return writer.Close()
	default:
		return fmt.Errorf("unsupported output format %q", format)
	}
}

// outputPathForFormat replaces or appends the extension for one output format.
// Parameters: outputBase is the user-supplied base path; format is the desired output type.
func outputPathForFormat(outputBase string, format OutputFormat) string {
	ext := "." + string(format)
	baseExt := filepath.Ext(outputBase)
	if baseExt == "" {
		return outputBase + ext
	}
	return strings.TrimSuffix(outputBase, baseExt) + ext
}

// outputPathForManifest returns the JSON path used by render-test manifest mode.
// Parameters: outputBase is the user-supplied base path.
func outputPathForManifest(outputBase string) string {
	baseExt := filepath.Ext(outputBase)
	if strings.EqualFold(baseExt, ".json") {
		return outputBase
	}
	if baseExt == "" {
		return outputBase + ".json"
	}
	return strings.TrimSuffix(outputBase, baseExt) + ".json"
}

func outputFormats(outputPath string, format string) ([]OutputFormat, error) {
	if outputPath != "" {
		switch strings.ToLower(filepath.Ext(outputPath)) {
		case ".png":
			return []OutputFormat{outputPNG}, nil
		case ".svg":
			return []OutputFormat{outputSVG}, nil
		default:
			return nil, errors.New("--output-path must end in .png or .svg when provided")
		}
	}
	return parseOutputFormats(format)
}

// parseOutputFormats parses a comma-separated list of output format names.
// Parameters: value is a list such as "png", "svg", or "png,svg".
func parseOutputFormats(value string) ([]OutputFormat, error) {
	var formats []OutputFormat
	seen := map[OutputFormat]bool{}
	for _, raw := range strings.Split(value, ",") {
		normalized := OutputFormat(strings.ToLower(strings.TrimSpace(raw)))
		if normalized == "" {
			continue
		}
		switch normalized {
		case outputPNG, outputSVG:
			if !seen[normalized] {
				formats = append(formats, normalized)
				seen[normalized] = true
			}
		default:
			return nil, fmt.Errorf("unsupported format %q; use --format png,svg", raw)
		}
	}
	if len(formats) == 0 {
		return nil, errors.New("no output formats specified; use --format png,svg")
	}
	return formats, nil
}

// readXMLFile opens and parses an XML file into the lightweight DOM model.
// Parameters: path is the XML file path to read.
func readXMLFile(path string) (*xmlElement, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	return parseXML(file)
}

// parseXML builds a lightweight element tree from an XML stream.
// Parameters: reader supplies XML tokens from an SBGNML file or compatible source.
func parseXML(reader io.Reader) (*xmlElement, error) {
	decoder := xml.NewDecoder(reader)
	var root *xmlElement
	var stack []*xmlElement
	for {
		token, err := decoder.Token()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, err
		}
		switch typed := token.(type) {
		case xml.StartElement:
			node := &xmlElement{
				Name:  typed.Name.Local,
				Attrs: map[string]string{},
			}
			for _, attr := range typed.Attr {
				node.Attrs[attr.Name.Local] = attr.Value
			}
			if len(stack) == 0 {
				root = node
			} else {
				parent := stack[len(stack)-1]
				parent.Children = append(parent.Children, node)
			}
			stack = append(stack, node)
		case xml.EndElement:
			if len(stack) == 0 {
				return nil, errors.New("unexpected XML end element")
			}
			stack = stack[:len(stack)-1]
		}
	}
	if root == nil {
		return nil, errors.New("empty XML document")
	}
	return root, nil
}

// childElements returns direct child elements for traversal.
// Parameters: element is the parent XML node.
func childElements(element *xmlElement) []*xmlElement {
	return element.Children
}

// elementAttr returns an attribute value or an empty string when missing.
// Parameters: element is the XML node; name is the local attribute name.
func elementAttr(element *xmlElement, name string) string {
	if element == nil || element.Attrs == nil {
		return ""
	}
	return element.Attrs[name]
}

// findFirstDescendant returns the first descendant element with a matching local name.
// Parameters: element is the root of the search; name is the local element name to match.
func findFirstDescendant(element *xmlElement, name string) *xmlElement {
	for _, child := range childElements(element) {
		if child.Name == name {
			return child
		}
		if found := findFirstDescendant(child, name); found != nil {
			return found
		}
	}
	return nil
}

// collectDescendantsByName appends all descendant elements with a matching local name.
// Parameters: element is the search root; name is the local element name; out receives matches.
func collectDescendantsByName(element *xmlElement, name string, out *[]*xmlElement) {
	for _, child := range childElements(element) {
		if child.Name == name {
			*out = append(*out, child)
		}
		collectDescendantsByName(child, name, out)
	}
}

// parseRenderInformation extracts optional SBGN renderInformation colors and styles.
// Parameters: root is the parsed SBGNML document root.
func parseRenderInformation(root *xmlElement) RenderInfo {
	info := RenderInfo{
		Styles: map[string]RenderStyle{},
		Colors: map[string]Color{},
	}
	renderNode := findFirstDescendant(root, "renderInformation")
	if renderNode == nil {
		return info
	}

	var colorDefs []*xmlElement
	collectDescendantsByName(renderNode, "colorDefinition", &colorDefs)
	for _, colorDef := range colorDefs {
		id := elementAttr(colorDef, "id")
		value := elementAttr(colorDef, "value")
		if id == "" || value == "" {
			continue
		}
		if color, ok := parseColorValue(value, info.Colors); ok {
			info.Colors[id] = color
		}
	}

	if background := elementAttr(renderNode, "background-color"); background != "" {
		if color, ok := parseColorValue(background, info.Colors); ok {
			info.BackgroundColor = &color
		}
	}

	var styleNodes []*xmlElement
	collectDescendantsByName(renderNode, "style", &styleNodes)
	for _, styleNode := range styleNodes {
		style := RenderStyle{}
		var gNode *xmlElement
		for _, child := range childElements(styleNode) {
			if child.Name == "g" {
				gNode = child
				break
			}
		}
		if gNode != nil {
			style.FontSize = parseOptionalFloat(elementAttr(gNode, "font-size"))
			style.FontFamily = elementAttr(gNode, "font-family")
			if value := elementAttr(gNode, "font-color"); value != "" {
				if color, ok := parseColorValue(value, info.Colors); ok {
					style.FontColor = &color
				}
			}
			if value := elementAttr(gNode, "stroke"); value != "" {
				if color, ok := parseColorValue(value, info.Colors); ok {
					style.StrokeColor = &color
				}
			}
			style.StrokeWidth = parseOptionalFloat(elementAttr(gNode, "stroke-width"))
			if value := elementAttr(gNode, "fill"); value != "" {
				if color, ok := parseColorValue(value, info.Colors); ok {
					style.FillColor = &color
				}
			}
			style.BackgroundOpacity = parseOptionalFloat(elementAttr(gNode, "background-opacity"))
		}

		idList := strings.Fields(elementAttr(styleNode, "idList"))
		if len(idList) == 0 {
			styleCopy := style
			info.DefaultStyle = &styleCopy
			continue
		}
		for _, id := range idList {
			info.Styles[id] = style
		}
	}
	return info
}

// parseColorValue resolves a color reference or hex literal.
// Parameters: value is a renderInformation color token; colors maps named colorDefinition ids.
func parseColorValue(value string, colors map[string]Color) (Color, bool) {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" || strings.EqualFold(trimmed, "none") {
		return Color{}, false
	}
	if color, ok := colors[trimmed]; ok {
		return color, true
	}
	if strings.HasPrefix(trimmed, "#") {
		return parseHexColor(trimmed)
	}
	return Color{}, false
}

// parseHexColor parses CSS-style #RGB, #RGBA, #RRGGBB, or #RRGGBBAA colors.
// Parameters: value is the hex color string, with or without leading whitespace.
func parseHexColor(value string) (Color, bool) {
	hexValue := strings.TrimPrefix(strings.TrimSpace(value), "#")
	var r, g, b, a uint8
	switch len(hexValue) {
	case 3:
		r = parseHexNibble(hexValue[0])
		g = parseHexNibble(hexValue[1])
		b = parseHexNibble(hexValue[2])
		a = 0xFF
	case 4:
		r = parseHexNibble(hexValue[0])
		g = parseHexNibble(hexValue[1])
		b = parseHexNibble(hexValue[2])
		a = parseHexNibble(hexValue[3])
	case 6:
		values, ok := parseHexBytes(hexValue)
		if !ok {
			return Color{}, false
		}
		r, g, b, a = values[0], values[1], values[2], 0xFF
	case 8:
		values, ok := parseHexBytes(hexValue)
		if !ok {
			return Color{}, false
		}
		r, g, b, a = values[0], values[1], values[2], values[3]
	default:
		return Color{}, false
	}
	return Color{
		R: float64(r) / 255.0,
		G: float64(g) / 255.0,
		B: float64(b) / 255.0,
		A: float64(a) / 255.0,
	}, true
}

func (styleConfig *StyleConfig) backgroundColor() *Color {
	if styleConfig == nil || strings.TrimSpace(styleConfig.BackgroundColor) == "" {
		return nil
	}
	if color, ok := parseHexColor(styleConfig.BackgroundColor); ok {
		return &color
	}
	return nil
}

func (styleConfig *StyleConfig) edgeColor() Color {
	if styleConfig != nil && strings.TrimSpace(styleConfig.EdgeColor) != "" {
		if color, ok := parseHexColor(styleConfig.EdgeColor); ok {
			return color
		}
	}
	return jsEdgeColor
}

func (styleConfig *StyleConfig) textColor() (Color, bool) {
	if styleConfig != nil && strings.TrimSpace(styleConfig.TextColor) != "" {
		return parseHexColor(styleConfig.TextColor)
	}
	return Color{}, false
}

func (styleConfig *StyleConfig) styleForClass(className string) (ClassStyle, bool) {
	if styleConfig == nil || styleConfig.Styles == nil {
		return ClassStyle{}, false
	}
	candidates := []string{className}
	if strings.HasSuffix(className, " multimer") {
		candidates = append(candidates, strings.TrimSuffix(className, " multimer"))
	}
	if strings.Contains(className, "macromolecule") {
		candidates = append(candidates, "macromolecule")
	}
	if strings.Contains(className, "simple chemical") {
		candidates = append(candidates, "simple chemical")
	}
	if strings.Contains(className, "complex") {
		candidates = append(candidates, "complex")
	}
	if strings.Contains(className, "process") || className == "association" || className == "dissociation" {
		candidates = append(candidates, "process")
	}
	candidates = append(candidates, "generic node")
	for _, candidate := range candidates {
		if style, ok := styleConfig.Styles[candidate]; ok {
			return style, true
		}
	}
	return ClassStyle{}, false
}

// parseHexNibble expands one hexadecimal digit to an 8-bit channel value.
// Parameters: value is the ASCII hex digit to parse.
func parseHexNibble(value byte) uint8 {
	digit, err := strconv.ParseUint(string(value), 16, 8)
	if err != nil {
		return 0
	}
	return uint8(digit) * 17
}

// parseHexBytes parses pairs of hexadecimal digits into bytes.
// Parameters: value is an even-length hex string without a leading '#'.
func parseHexBytes(value string) ([]uint8, bool) {
	if len(value)%2 != 0 {
		return nil, false
	}
	values := make([]uint8, 0, len(value)/2)
	for i := 0; i < len(value); i += 2 {
		parsed, err := strconv.ParseUint(value[i:i+2], 16, 8)
		if err != nil {
			return nil, false
		}
		values = append(values, uint8(parsed))
	}
	return values, true
}

// parseSBGN normalizes SBGN glyphs, arcs, and diagram bounds from XML.
// Parameters: root is the parsed SBGNML document root.
func parseSBGN(root *xmlElement) ([]Glyph, []Arc, Bounds, error) {
	var arcNodes []*xmlElement
	collectDescendantsByName(root, "arc", &arcNodes)

	var mapNodes []*xmlElement
	collectDescendantsByName(root, "map", &mapNodes)
	if len(mapNodes) == 0 {
		return nil, nil, Bounds{}, errors.New("SBGN file missing map element")
	}

	var glyphs []Glyph
	for _, mapNode := range mapNodes {
		for _, node := range childElements(mapNode) {
			if node.Name == "glyph" {
				parseGlyphNode(node, "", &glyphs)
			}
		}
	}

	var arcs []Arc
	for _, arcNode := range arcNodes {
		arc, err := parseArcNode(arcNode)
		if err != nil {
			return nil, nil, Bounds{}, err
		}
		arcs = append(arcs, arc)
	}

	bounds, err := computeBounds(glyphs, arcs)
	if err != nil {
		return nil, nil, Bounds{}, err
	}
	return glyphs, arcs, bounds, nil
}

// parseArcNode converts one SBGN <arc> element into an Arc polyline.
// Parameters: arcNode is the XML arc element to parse.
func parseArcNode(arcNode *xmlElement) (Arc, error) {
	var startNode *xmlElement
	var endNode *xmlElement
	var nextNodes []*xmlElement
	for _, child := range childElements(arcNode) {
		switch child.Name {
		case "start":
			startNode = child
		case "end":
			endNode = child
		case "next":
			nextNodes = append(nextNodes, child)
		}
	}
	if startNode == nil {
		return Arc{}, errors.New("arc missing start")
	}
	if endNode == nil {
		return Arc{}, errors.New("arc missing end")
	}

	startX, ok := parseFloat(elementAttr(startNode, "x"))
	if !ok {
		return Arc{}, errors.New("bad arc start x")
	}
	startY, ok := parseFloat(elementAttr(startNode, "y"))
	if !ok {
		return Arc{}, errors.New("bad arc start y")
	}
	points := []Point{{X: startX, Y: startY}}
	for _, nextNode := range nextNodes {
		x, okX := parseFloat(elementAttr(nextNode, "x"))
		y, okY := parseFloat(elementAttr(nextNode, "y"))
		if okX && okY {
			points = append(points, Point{X: x, Y: y})
		}
	}
	endX, ok := parseFloat(elementAttr(endNode, "x"))
	if !ok {
		return Arc{}, errors.New("bad arc end x")
	}
	endY, ok := parseFloat(elementAttr(endNode, "y"))
	if !ok {
		return Arc{}, errors.New("bad arc end y")
	}
	points = append(points, Point{X: endX, Y: endY})

	return Arc{
		ID:        elementAttr(arcNode, "id"),
		ClassName: elementAttr(arcNode, "class"),
		Source:    elementAttr(arcNode, "source"),
		Target:    elementAttr(arcNode, "target"),
		Points:    points,
	}, nil
}

// parseGlyphNode flattens one SBGN <glyph> subtree into the glyph slice.
// Parameters: glyphNode is the XML glyph element; parentID links nested glyphs; glyphs receives parsed glyph records.
func parseGlyphNode(glyphNode *xmlElement, parentID string, glyphs *[]Glyph) {
	id := elementAttr(glyphNode, "id")
	className := elementAttr(glyphNode, "class")
	label := ""
	var bbox *BBox
	var ports []Port
	hasClone := false
	stateValue := ""
	stateVariable := ""

	for _, child := range childElements(glyphNode) {
		switch child.Name {
		case "label":
			label = strings.ReplaceAll(elementAttr(child, "text"), "\r", "")
		case "bbox":
			bbox = parseBBox(child)
		case "port":
			x, okX := parseFloat(elementAttr(child, "x"))
			y, okY := parseFloat(elementAttr(child, "y"))
			if okX && okY {
				ports = append(ports, Port{ID: elementAttr(child, "id"), Point: Point{X: x, Y: y}})
			}
		case "clone":
			hasClone = true
		case "state":
			stateValue = elementAttr(child, "value")
			stateVariable = elementAttr(child, "variable")
		}
	}

	*glyphs = append(*glyphs, Glyph{
		ID:            id,
		ParentID:      parentID,
		ClassName:     className,
		BBox:          bbox,
		Label:         label,
		Ports:         ports,
		HasClone:      hasClone,
		StateValue:    stateValue,
		StateVariable: stateVariable,
		Orientation:   elementAttr(glyphNode, "orientation"),
	})

	for _, child := range childElements(glyphNode) {
		if child.Name == "glyph" {
			parseGlyphNode(child, id, glyphs)
		}
	}
}

// parseBBox parses a <bbox> element into a BBox.
// Parameters: node is the XML bbox element.
func parseBBox(node *xmlElement) *BBox {
	x, okX := parseFloat(elementAttr(node, "x"))
	y, okY := parseFloat(elementAttr(node, "y"))
	w, okW := parseFloat(elementAttr(node, "w"))
	h, okH := parseFloat(elementAttr(node, "h"))
	if !okX || !okY || !okW || !okH {
		return nil
	}
	return &BBox{X: x, Y: y, W: w, H: h}
}

// parseFloat parses a required floating-point attribute value.
// Parameters: value is the attribute string to parse.
func parseFloat(value string) (float64, bool) {
	if strings.TrimSpace(value) == "" {
		return 0, false
	}
	parsed, err := strconv.ParseFloat(value, 64)
	return parsed, err == nil
}

// parseOptionalFloat parses an optional floating-point attribute.
// Parameters: value is the attribute string; empty or invalid values return nil.
func parseOptionalFloat(value string) *float64 {
	parsed, ok := parseFloat(value)
	if !ok {
		return nil
	}
	return &parsed
}

// computeBounds finds the extents of JS-visible glyph boxes used by Cytoscape fit.
// Parameters: glyphs contains all parsed glyphs; arcs is retained for signature parity.
func computeBounds(glyphs []Glyph, arcs []Arc) (Bounds, error) {
	var xValues []float64
	var yValues []float64
	for _, glyph := range glyphs {
		if glyph.BBox != nil && !isJSHiddenGlyphClass(glyph.ClassName) {
			bbox := *glyph.BBox
			xValues = append(xValues, bbox.X, bbox.X+bbox.W)
			yValues = append(yValues, bbox.Y, bbox.Y+bbox.H)
		}
	}
	if len(xValues) == 0 || len(yValues) == 0 {
		return Bounds{}, errors.New("no coordinates found in SBGN file")
	}
	sort.Float64s(xValues)
	sort.Float64s(yValues)
	return Bounds{
		MinX: xValues[0],
		MaxX: xValues[len(xValues)-1],
		MinY: yValues[0],
		MaxY: yValues[len(yValues)-1],
	}, nil
}

// transformWithPadding expands bounds and returns the output transform and size.
// Parameters: bounds are logical diagram extents; padding is added on every side.
func transformWithPadding(bounds Bounds, padding float64, outputWidth float64, outputHeight float64) (Transform, float64, float64) {
	minX := bounds.MinX - padding
	maxX := bounds.MaxX + padding
	minY := bounds.MinY - padding
	maxY := bounds.MaxY + padding
	spanX := math.Max(math.Abs(maxX-minX), 1.0)
	spanY := math.Max(math.Abs(maxY-minY), 1.0)
	width := math.Max(outputWidth, spanX)
	height := math.Max(outputHeight, spanY)
	if outputWidth > 0 {
		width = outputWidth
	}
	if outputHeight > 0 {
		height = outputHeight
	}
	scale := math.Min(width/spanX, height/spanY)
	transform := Transform{
		MinX:    minX,
		MinY:    minY,
		ScaleX:  scale,
		ScaleY:  scale,
		OffsetX: (width - spanX*scale) / 2.0,
		OffsetY: (height - spanY*scale) / 2.0,
	}
	return transform, width, height
}

// computeTagOrientations infers which side of a tag should contain the notch.
// Parameters: glyphs contains candidate tag glyphs; arcs provide connected endpoints.
func computeTagOrientations(glyphs []Glyph, arcs []Arc) map[string]TagOrientation {
	orientations := map[string]TagOrientation{}
	for _, glyph := range glyphs {
		if glyph.ClassName != "tag" || glyph.BBox == nil {
			continue
		}
		var bestDistance float64
		var bestOrientation TagOrientation
		found := false
		for _, arc := range arcs {
			matches, point := matchArcConnection(arc, glyph.ID)
			if !matches || point == nil {
				continue
			}
			distLeft := math.Abs(point.X - glyph.BBox.X)
			distRight := math.Abs(point.X - (glyph.BBox.X + glyph.BBox.W))
			distance := distLeft
			orientation := tagLeft
			if distRight < distLeft {
				distance = distRight
				orientation = tagRight
			}
			if !found || distance < bestDistance {
				found = true
				bestDistance = distance
				bestOrientation = orientation
			}
		}
		if !found {
			bestOrientation = tagLeft
		}
		orientations[glyph.ID] = bestOrientation
	}
	return orientations
}

// matchArcConnection checks whether an arc endpoint references a glyph or glyph port.
// Parameters: arc is the candidate arc; glyphID is the glyph id to match.
func matchArcConnection(arc Arc, glyphID string) (bool, *Point) {
	if arcRefMatches(arc.Source, glyphID) {
		if len(arc.Points) == 0 {
			return true, nil
		}
		point := arc.Points[0]
		return true, &point
	}
	if arcRefMatches(arc.Target, glyphID) {
		if len(arc.Points) == 0 {
			return true, nil
		}
		point := arc.Points[len(arc.Points)-1]
		return true, &point
	}
	return false, nil
}

// arcRefMatches reports whether an arc source/target reference points to a glyph.
// Parameters: arcRef is an SBGN endpoint id; glyphID is the glyph id to compare.
func arcRefMatches(arcRef string, glyphID string) bool {
	return arcRef == glyphID || strings.HasPrefix(arcRef, glyphID+".")
}

// renderSBGNML draws the complete normalized SBGN diagram in deterministic order.
// Parameters: r owns the canvas context; transform maps logical coordinates; glyphs/arcs are parsed SBGN data; renderInfo supplies styles; tagOrientations supplies inferred notches; showCloneMarkers toggles clone overlays.
func (r renderer) renderSBGNML(transform *Transform, glyphs []Glyph, arcs []Arc, renderInfo RenderInfo, tagOrientations map[string]TagOrientation, showCloneMarkers bool, glyphColors map[string]string, glyphColorType GlyphColorType, autoContrastText bool, styleConfig *StyleConfig) error {
	_ = renderInfo
	_ = tagOrientations
	_ = showCloneMarkers

	glyphByID := map[string]*Glyph{}
	portParentByID := map[string]string{}
	for index := range glyphs {
		glyph := &glyphs[index]
		if _, exists := glyphByID[glyph.ID]; exists {
			continue
		}
		glyphByID[glyph.ID] = glyph
		for _, port := range glyph.Ports {
			if port.ID != "" {
				portParentByID[port.ID] = glyph.ID
			}
		}
	}

	for index := range glyphs {
		glyph := &glyphs[index]
		if glyph.ClassName == "compartment" && glyphByID[glyph.ID] == glyph {
			r.drawJSGlyph(transform, glyph, glyphColors, glyphColorType, autoContrastText, styleConfig)
		}
	}
	for _, arc := range arcs {
		r.drawJSArc(transform, arc, glyphByID, portParentByID, styleConfig)
	}
	for index := range glyphs {
		glyph := &glyphs[index]
		if glyph.ClassName != "compartment" && glyphByID[glyph.ID] == glyph {
			r.drawJSGlyph(transform, glyph, glyphColors, glyphColorType, autoContrastText, styleConfig)
		}
	}
	return nil
}

// drawJSGlyph draws a glyph using the same primitive style as the JS/R baseline.
// Parameters: transform maps SBGN coordinates; glyph is the parsed glyph; glyphColors maps labels or IDs to hex fill colors.
func (r renderer) drawJSGlyph(transform *Transform, glyph *Glyph, glyphColors map[string]string, glyphColorType GlyphColorType, autoContrastText bool, styleConfig *StyleConfig) {
	if glyph.BBox == nil || isJSHiddenGlyphClass(glyph.ClassName) {
		return
	}
	rect := bboxPixelRect(transform, *glyph.BBox)
	style := jsStyleForGlyphWithColors(glyph, glyphColors, glyphColorType, autoContrastText, styleConfig)
	path := jsShapePath(rect, style.Shape)
	r.drawJSPath(path, style.Fill, style.Border, style.BorderWidth, style.Dashed)
	if strings.TrimSpace(style.Label) == "" {
		return
	}
	textScale := math.Min(1.0, transform.scaleScalar(1.0))
	renderedFontPx := math.Max(5.0, style.FontPx*textScale)
	labelCenter := rect.Center
	if style.LabelValign == "top" {
		labelCenter.Y = rect.Y0 + math.Max(8.0, renderedFontPx)
	}
	r.drawTextCentered(labelCenter, style.Label, renderedFontPx, style.TextColor)
}

// jsShapePath creates a JS baseline primitive path.
// Parameters: rect is the output rectangle; shape is the primitive type.
func jsShapePath(rect PixelRect, shape string) *canvas.Path {
	switch shape {
	case "ellipse":
		return ellipsePath(rect)
	case "rectangle":
		return rectPath(rect)
	case "hexagon":
		return hexagonPath(rect)
	default:
		radius := math.Max(math.Min(rect.Width, rect.Height)*0.1, 1.0)
		return roundRectPath(rect, radius)
	}
}

// drawJSPath draws a JS primitive shape with optional dashed stroke.
// Parameters: path is geometry; fill/stroke/width/dashed are visual styles.
func (r renderer) drawJSPath(path *canvas.Path, fill *Color, stroke Color, width float64, dashed bool) {
	if fill != nil {
		r.ctx.SetFill(fill.canvasColor())
	} else {
		r.ctx.SetFill(nil)
	}
	r.ctx.SetStroke(stroke.canvasColor())
	r.ctx.SetStrokeWidth(width)
	if dashed {
		r.ctx.SetDashes(0.0, 6.0, 3.0)
	} else {
		r.ctx.SetDashes(0.0)
	}
	r.ctx.DrawPath(0, 0, path)
	r.ctx.SetDashes(0.0)
}

// drawJSArc draws one JS baseline edge line and marker.
// Parameters: transform maps SBGN coordinates; arc is parsed; glyphByID/portParentByID resolve endpoints.
func (r renderer) drawJSArc(transform *Transform, arc Arc, glyphByID map[string]*Glyph, portParentByID map[string]string, styleConfig *StyleConfig) {
	points, _, _, ok := jsArcPoints(arc, glyphByID, portParentByID)
	if !ok {
		return
	}
	start := transform.mapPoint(points[0].X, points[0].Y)
	end := transform.mapPoint(points[1].X, points[1].Y)
	path := &canvas.Path{}
	path.MoveTo(start.X, start.Y)
	path.LineTo(end.X, end.Y)
	edgeColor := styleConfig.edgeColor()
	r.drawPath(path, nil, &edgeColor, 1.3)
	marker := jsArcMarker(arc.ClassName)
	if marker == "triangle" {
		r.drawFilledTriangle(end, start, transform.scaleScalar(arrowSize), edgeColor)
	} else if marker == "tee" {
		r.drawInhibitionBar(end, start, transform.scaleScalar(barLength), 0.0, edgeColor, 1.3)
	} else if marker == "circle" {
		radius := math.Max(transform.scaleScalar(arrowSize)*0.4, 1.0)
		r.drawPath(circlePath(end, radius), &edgeColor, &edgeColor, 1.3)
	}
}

// drawFilledTriangle draws a filled production arrow marker.
// Parameters: r owns the canvas context; end is marker tip; prev gives arc direction; size controls marker length; fill is marker color.
func (r renderer) drawFilledTriangle(end Point, prev Point, size float64, fill Color) {
	p1, p2, tip, ok := trianglePoints(end, prev, size)
	if !ok {
		return
	}
	path := &canvas.Path{}
	path.MoveTo(p1.X, p1.Y)
	path.LineTo(p2.X, p2.Y)
	path.LineTo(tip.X, tip.Y)
	path.Close()
	r.drawPath(path, &fill, nil, 0.0)
}

// trianglePoints computes a triangle marker from an arc direction.
// Parameters: end is the marker tip; prev is the prior arc point; size controls marker length.
func trianglePoints(end Point, prev Point, size float64) (Point, Point, Point, bool) {
	dx := end.X - prev.X
	dy := end.Y - prev.Y
	length := math.Hypot(dx, dy)
	if length == 0.0 {
		return Point{}, Point{}, Point{}, false
	}
	ux := dx / length
	uy := dy / length
	baseX := end.X - ux*size
	baseY := end.Y - uy*size
	perpX := -uy
	perpY := ux
	halfWidth := size * 0.6
	return Point{X: baseX + perpX*halfWidth, Y: baseY + perpY*halfWidth},
		Point{X: baseX - perpX*halfWidth, Y: baseY - perpY*halfWidth},
		end,
		true
}

// drawInhibitionBar draws an inhibition bar perpendicular to an arc direction.
// Parameters: r owns the canvas context; end is the arc endpoint; prev gives arc direction; length sizes the bar; offset moves it back from the endpoint; strokeColor/strokeWidth style it.
func (r renderer) drawInhibitionBar(end Point, prev Point, length float64, offset float64, strokeColor Color, strokeWidth float64) {
	dx := end.X - prev.X
	dy := end.Y - prev.Y
	segLen := math.Hypot(dx, dy)
	if segLen == 0.0 {
		return
	}
	ux := dx / segLen
	uy := dy / segLen
	centerX := end.X - ux*offset
	centerY := end.Y - uy*offset
	perpX := -uy
	perpY := ux
	halfLen := length / 2.0
	path := &canvas.Path{}
	path.MoveTo(centerX-perpX*halfLen, centerY-perpY*halfLen)
	path.LineTo(centerX+perpX*halfLen, centerY+perpY*halfLen)
	r.drawPath(path, nil, &strokeColor, strokeWidth)
}

// drawPath applies fill/stroke settings and draws a canvas path.
// Parameters: r owns the canvas context; path is the geometry; fillColor may be nil; strokeColor may be nil; strokeWidth is ignored when no stroke is set.
func (r renderer) drawPath(path *canvas.Path, fillColor *Color, strokeColor *Color, strokeWidth float64) {
	if path == nil || path.Empty() {
		return
	}
	if fillColor != nil {
		r.ctx.SetFill(fillColor.canvasColor())
	} else {
		r.ctx.SetFill(nil)
	}
	if strokeColor != nil && strokeWidth > 0.0 {
		r.ctx.SetStroke(strokeColor.canvasColor())
		r.ctx.SetStrokeWidth(strokeWidth)
	} else {
		r.ctx.SetStroke(nil)
		r.ctx.SetStrokeWidth(0.0)
	}
	r.ctx.DrawPath(0, 0, path)
}

// drawTextCentered draws a single-line label centered on a point.
// Parameters: r owns the canvas context; center is the output anchor; text is the label; fontPx is logical font size; fontColor styles text.
func (r renderer) drawTextCentered(center Point, text string, fontPx float64, fontColor Color) {
	if strings.TrimSpace(text) == "" {
		return
	}
	face := r.fontFamily.Face(fontPx*ptPerMm, fontColor.canvasColor(), canvas.FontRegular, canvas.FontNormal)
	textObject := canvas.NewTextBox(face, text, 0.0, 0.0, canvas.Center, canvas.Middle, nil)
	bounds := textObject.Bounds()
	x := center.X - bounds.W()/2.0 - bounds.X0
	y := center.Y - bounds.H()/2.0 - bounds.Y0
	r.ctx.DrawText(x, y, textObject)
}

// bboxPixelRect maps a logical SBGN bbox into a normalized output rectangle.
// Parameters: transform maps logical coordinates; bbox is the SBGN bounding box.
func bboxPixelRect(transform *Transform, bbox BBox) PixelRect {
	x0 := transform.OffsetX + (bbox.X-transform.MinX)*transform.ScaleX
	x1 := transform.OffsetX + (bbox.X+bbox.W-transform.MinX)*transform.ScaleX
	y0 := transform.OffsetY + (bbox.Y-transform.MinY)*transform.ScaleY
	y1 := transform.OffsetY + (bbox.Y+bbox.H-transform.MinY)*transform.ScaleY
	left := math.Min(x0, x1)
	right := math.Max(x0, x1)
	top := math.Min(y0, y1)
	bottom := math.Max(y0, y1)
	return PixelRect{
		X0:     left,
		Y0:     top,
		Width:  right - left,
		Height: bottom - top,
		Center: Point{X: (left + right) / 2.0, Y: (top + bottom) / 2.0},
	}
}

// ptrColor returns a pointer to a color value for optional-style calls.
// Parameters: color is the color value to reference.
func ptrColor(color Color) *Color {
	return &color
}

// rectPath builds a rectangular canvas path.
// Parameters: rect is the output rectangle to trace.
func rectPath(rect PixelRect) *canvas.Path {
	path := &canvas.Path{}
	path.MoveTo(rect.X0, rect.Y0)
	path.LineTo(rect.X0+rect.Width, rect.Y0)
	path.LineTo(rect.X0+rect.Width, rect.Y0+rect.Height)
	path.LineTo(rect.X0, rect.Y0+rect.Height)
	path.Close()
	return path
}

// ellipsePath builds an ellipse path fitted to a rectangle.
// Parameters: rect is the output rectangle that bounds the ellipse.
func ellipsePath(rect PixelRect) *canvas.Path {
	return canvas.Ellipse(math.Max(rect.Width/2.0, 1.0), math.Max(rect.Height/2.0, 1.0)).Translate(rect.Center.X, rect.Center.Y)
}

// circlePath builds a circle path around a center point.
// Parameters: center is the output center point; radius is the circle radius.
func circlePath(center Point, radius float64) *canvas.Path {
	return canvas.Circle(math.Max(radius, 1.0)).Translate(center.X, center.Y)
}

// roundRectPath builds a rounded rectangle path.
// Parameters: rect is the output rectangle; radius is the requested corner radius.
func roundRectPath(rect PixelRect, radius float64) *canvas.Path {
	radius = math.Min(radius, rect.Width/2.0)
	radius = math.Min(radius, rect.Height/2.0)
	return canvas.RoundedRectangle(rect.Width, rect.Height, radius).Translate(rect.X0, rect.Y0)
}

// hexagonPath builds a convex phenotype-style hexagon.
// Parameters: rect is the output rectangle that bounds the hexagon.
func hexagonPath(rect PixelRect) *canvas.Path {
	x0 := rect.X0
	y0 := rect.Y0
	w := rect.Width
	h := rect.Height
	points := []Point{
		{X: x0, Y: y0 + 0.5*h},
		{X: x0 + 0.25*w, Y: y0},
		{X: x0 + 0.75*w, Y: y0},
		{X: x0 + w, Y: y0 + 0.5*h},
		{X: x0 + 0.75*w, Y: y0 + h},
		{X: x0 + 0.25*w, Y: y0 + h},
	}
	return polygonPath(points)
}

// polygonPath builds a closed polygon path from ordered points.
// Parameters: points are output vertices in drawing order.
func polygonPath(points []Point) *canvas.Path {
	path := &canvas.Path{}
	if len(points) == 0 {
		return path
	}
	path.MoveTo(points[0].X, points[0].Y)
	for _, point := range points[1:] {
		path.LineTo(point.X, point.Y)
	}
	path.Close()
	return path
}
