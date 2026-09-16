#pragma once

#include <map>
#include <string>
#include <vector>

namespace novex
{

// A deliberately small YAML reader.
//
// Rationale: the two files Novex needs to read (the existing stereo
// calibration and the runtime config) use a tiny, stable subset of
// YAML. Pulling in yaml-cpp for that would add a dependency to a
// project whose stated rule is that every dependency needs a reason,
// and OpenCV's FileStorage cannot read these files because they lack
// its %YAML:1.0 header and use plain block sequences.
//
// Supported subset:
//
//   key: value              scalars, optionally quoted
//   key:                    nested block maps, by indentation
//     child: value
//   key:                    block sequences of scalars
//   - 1.0
//   - 2.0
//   # comments              to end of line
//
// NOT supported: flow collections ({a: 1}, [1, 2]) other than the
// empty forms {} and [], anchors, multi-line strings, sequences of
// maps. Anything unsupported is reported as a parse error rather than
// being silently misread, which matters when the data is a
// calibration.
class Yaml
{
public:

    bool loadFile(const std::string& path);
    bool loadString(const std::string& text);

    // Keys are dotted paths: "camera1.K", "rms.left".
    bool has(const std::string& key) const;

    std::string getString(const std::string& key,
                          const std::string& fallback = "") const;

    double getDouble(const std::string& key, double fallback) const;
    int    getInt(const std::string& key, int fallback) const;
    bool   getBool(const std::string& key, bool fallback) const;

    // Returns an empty vector if the key is absent or is not a
    // sequence.
    std::vector<double> getVector(const std::string& key) const;

    const std::string& error() const { return errorMessage; }

private:

    std::map<std::string, std::string> scalars;
    std::map<std::string, std::vector<double>> sequences;

    std::string errorMessage;
};

} // namespace novex
